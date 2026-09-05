"""File upload and ingestion control.

The request path does the minimum: checksum, store the bytes, write a row,
enqueue. Everything expensive happens in the Celery worker. A 200 here means
"accepted", not "searchable" - the client polls status or watches the SSE
progress channel.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.api.deps import CurrentUser, DbSession, RequestId
from app.config import settings
from app.core.logging import get_logger
from app.db.repositories import AuditRepository, DocumentRepository
from app.ingestion.tasks import ingest_document, purge_document
from app.llm.registry import get_embedder
from app.schemas.common import DocumentOut, SearchRequest
from app.search.hybrid import hybrid_search
from app.storage.object_store import checksum, get_object_store

router = APIRouter(tags=["files"])
log = get_logger(__name__)

ALLOWED_SUFFIXES = {".pdf", ".docx", ".doc", ".txt", ".md", ".csv", ".xlsx", ".xls", ".json", ".html", ".htm"}


@router.post("/files", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    session: DbSession,
    user: CurrentUser,
    req_id: RequestId,
    file: UploadFile = File(...),
    conversation_id: uuid.UUID | None = Form(default=None),
    tags: str = Form(default=""),
) -> DocumentOut:
    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(ALLOWED_SUFFIXES)}",
        )

    data = await file.read()
    if len(data) > settings.storage.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.storage.max_upload_bytes // (1024 * 1024)} MB limit.",
        )

    digest = checksum(data)
    repo = DocumentRepository(session)

    existing = await repo.by_checksum(user, digest)
    if existing and existing.status == "indexed":
        # Identical bytes already ingested - hand back the existing document
        # instead of paying to embed it twice.
        return DocumentOut.model_validate(existing)

    key = f"{user}/{digest[:2]}/{digest}{suffix}"
    await get_object_store().put(key, data, file.content_type or "application/octet-stream")

    document = existing or await repo.create(
        user_id=user,
        conversation_id=conversation_id,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        checksum_sha256=digest,
        storage_backend=settings.storage.backend,
        storage_key=key,
        status="queued",
        meta={"tags": [t.strip() for t in tags.split(",") if t.strip()], "request_id": req_id},
    )

    job = await repo.add_job(document_id=document.id, task_id="pending", stage="queued")
    await session.flush()

    task = ingest_document.apply_async(args=[str(document.id), str(job.id)], queue="ingest")
    job.task_id = task.id
    document.celery_task_id = task.id

    await AuditRepository(session).record(
        action="file.upload", resource_type="document", resource_id=str(document.id),
        user_id=user, request_id=req_id,
        detail={"filename": document.filename, "bytes": len(data), "task_id": task.id},
    )
    log.info("file_queued", document_id=str(document.id), task_id=task.id, bytes=len(data))
    # Refresh so server-generated defaults (created_at, updated_at) are loaded
    # before Pydantic serialises; avoids a MissingGreenlet on lazy access.
    await session.refresh(document)
    return DocumentOut.model_validate(document)


@router.get("/files", response_model=dict)
async def list_files(
    session: DbSession, user: CurrentUser, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
) -> dict:
    rows, total = await DocumentRepository(session).list_for_user(user, limit=limit, offset=offset)
    return {"items": [DocumentOut.model_validate(r) for r in rows], "total": total,
            "limit": limit, "offset": offset}


@router.get("/files/{document_id}", response_model=DocumentOut)
async def get_file(document_id: uuid.UUID, session: DbSession, user: CurrentUser) -> DocumentOut:
    document = await DocumentRepository(session).get(document_id)
    if document.user_id != user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentOut.model_validate(document)


@router.get("/files/{document_id}/download")
async def download_file(document_id: uuid.UUID, session: DbSession, user: CurrentUser) -> dict:
    document = await DocumentRepository(session).get(document_id)
    if document.user_id != user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {"url": await get_object_store().presigned_url(document.storage_key)}


@router.delete("/files/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(document_id: uuid.UUID, session: DbSession, user: CurrentUser, req_id: RequestId) -> None:
    repo = DocumentRepository(session)
    document = await repo.get(document_id)
    if document.user_id != user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    key = document.storage_key
    await repo.delete(document_id)
    purge_document.apply_async(args=[str(document_id)])
    await get_object_store().delete(key)
    await AuditRepository(session).record(
        action="file.delete", resource_type="document", resource_id=str(document_id),
        user_id=user, request_id=req_id, detail={"filename": document.filename},
    )


@router.post("/files/{document_id}/reingest", status_code=status.HTTP_202_ACCEPTED)
async def reingest(document_id: uuid.UUID, session: DbSession, user: CurrentUser) -> dict:
    repo = DocumentRepository(session)
    document = await repo.get(document_id)
    if document.user_id != user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    job = await repo.add_job(document_id=document.id, task_id="pending", stage="queued")
    await session.flush()
    task = ingest_document.apply_async(args=[str(document.id), str(job.id)], queue="ingest")
    job.task_id = task.id
    await repo.set_status(document_id, "queued", error=None, celery_task_id=task.id)
    return {"document_id": str(document_id), "task_id": task.id}


@router.post("/search")
async def search(body: SearchRequest, user: CurrentUser) -> dict:
    """Direct hybrid search, outside of any agent. Useful for debugging retrieval."""
    hits = await hybrid_search(
        body.query,
        embedder=get_embedder(),
        user_id=user,
        document_ids=body.document_ids,
        top_k=body.top_k,
        rerank=body.rerank,
    )
    return {"query": body.query, "hits": [h.to_dict() for h in hits]}
