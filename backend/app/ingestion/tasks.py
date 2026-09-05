"""The ingestion pipeline.

    upload (API) -> S3/MinIO -> Redis queue -> Celery worker
        -> parse -> chunk -> embed (batched) -> bulk index into OpenSearch
        -> status back to Postgres

Retries are Celery's `autoretry_for` with exponential backoff and jitter. Chunk
ids are deterministic (`{document_id}:{chunk_index}`) so a retried task
overwrites rather than duplicates - that idempotency is what makes acks_late
safe.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from celery import states
from celery.exceptions import Ignore, SoftTimeLimitExceeded
from opensearchpy import OpenSearch, helpers
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.models import Document, IngestionJob
from app.ingestion.celery_app import celery_app
from app.ingestion.chunking import chunk_pages
from app.ingestion.parsers import parse
from app.llm.registry import EmbeddingClient
from app.storage.object_store import get_object_store

configure_logging(settings.log_level, settings.log_format)
log = get_logger(__name__)

# Workers are sync; they get their own engine and their own OpenSearch client.
_engine = create_engine(settings.database.sync_dsn, pool_pre_ping=True, pool_size=5)
_Session = sessionmaker(bind=_engine, expire_on_commit=False)


def _os_client() -> OpenSearch:
    return OpenSearch(
        hosts=[{"host": settings.opensearch.host, "port": settings.opensearch.port}],
        http_auth=(settings.opensearch.user, settings.opensearch.password),
        use_ssl=settings.opensearch.use_ssl,
        verify_certs=settings.opensearch.verify_certs,
        ssl_show_warn=False,
        timeout=60,
    )


def _set_status(session: Session, document_id: uuid.UUID, status: str, **fields: Any) -> None:
    session.execute(update(Document).where(Document.id == document_id).values(status=status, **fields))
    session.commit()


def _progress(session: Session, job_id: uuid.UUID, stage: str, progress: float) -> None:
    session.execute(
        update(IngestionJob).where(IngestionJob.id == job_id).values(stage=stage, progress=progress, status="running")
    )
    session.commit()


@celery_app.task(
    bind=True,
    name="app.ingestion.tasks.ingest_document",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=4,
)
def ingest_document(self: Any, document_id: str, job_id: str) -> dict[str, Any]:
    doc_uuid = uuid.UUID(document_id)
    job_uuid = uuid.UUID(job_id)
    attempt = self.request.retries + 1
    log.info("ingest_started", document_id=document_id, attempt=attempt)

    session = _Session()
    try:
        document = session.get(Document, doc_uuid)
        if document is None:
            raise Ignore()

        _set_status(session, doc_uuid, "parsing", celery_task_id=self.request.id)
        _progress(session, job_uuid, "parsing", 0.1)

        raw = get_object_store().get_sync(document.storage_key)
        pages = parse(raw, document.filename, document.content_type)
        if not any(p.text.strip() for p in pages):
            _set_status(session, doc_uuid, "failed", error="No extractable text found in the document.")
            return {"status": "failed", "reason": "empty"}

        _set_status(session, doc_uuid, "chunking", page_count=len(pages))
        _progress(session, job_uuid, "chunking", 0.3)
        chunks = chunk_pages(pages)
        if not chunks:
            _set_status(session, doc_uuid, "failed", error="Document produced no chunks.")
            return {"status": "failed", "reason": "no_chunks"}

        _set_status(session, doc_uuid, "embedding")
        _progress(session, job_uuid, "embedding", 0.5)

        embedder = EmbeddingClient()
        batch = settings.ingestion.embedding_batch_size
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), batch):
            window = [c.text for c in chunks[start:start + batch]]
            vectors.extend(embedder.embed_documents_sync(window))
            _progress(session, job_uuid, "embedding", 0.5 + 0.35 * (start + batch) / max(len(chunks), 1))

        _set_status(session, doc_uuid, "indexing")
        _progress(session, job_uuid, "indexing", 0.9)

        now = datetime.now(UTC).isoformat()
        actions = [
            {
                "_op_type": "index",
                "_index": settings.opensearch.documents_index,
                "_id": f"{document_id}:{chunk.index}",   # deterministic => idempotent
                "_source": {
                    "document_id": document_id,
                    "chunk_id": f"{document_id}:{chunk.index}",
                    "user_id": document.user_id,
                    "conversation_id": str(document.conversation_id) if document.conversation_id else None,
                    "filename": document.filename,
                    "title": document.filename,
                    "content": chunk.text,
                    "embedding": vector,
                    "page": chunk.page,
                    "chunk_index": chunk.index,
                    "token_count": chunk.token_estimate,
                    "content_type": document.content_type,
                    "tags": (document.meta or {}).get("tags", []),
                    "checksum": document.checksum_sha256,
                    "created_at": now,
                    "metadata": document.meta or {},
                },
            }
            for chunk, vector in zip(chunks, vectors, strict=False)
        ]

        client = _os_client()
        success, errors = helpers.bulk(client, actions, chunk_size=200, request_timeout=120, raise_on_error=False)
        client.indices.refresh(index=settings.opensearch.documents_index)

        if errors:
            log.warning("bulk_partial_failure", document_id=document_id, failed=len(errors))

        _set_status(
            session, doc_uuid, "indexed", chunk_count=int(success),
            error=f"{len(errors)} chunks failed to index" if errors else None,
        )
        session.execute(
            update(IngestionJob).where(IngestionJob.id == job_uuid).values(
                stage="done", progress=1.0, status="succeeded", attempt=attempt
            )
        )
        session.commit()
        log.info("ingest_finished", document_id=document_id, chunks=int(success), pages=len(pages))
        return {"status": "indexed", "chunks": int(success), "pages": len(pages)}

    except SoftTimeLimitExceeded:
        _set_status(session, doc_uuid, "failed", error="Ingestion exceeded its time limit.")
        session.execute(
            update(IngestionJob).where(IngestionJob.id == job_uuid).values(status="failed", error="soft_time_limit")
        )
        session.commit()
        self.update_state(state=states.FAILURE, meta={"reason": "soft_time_limit"})
        raise
    except Ignore:
        raise
    except Exception as exc:
        log.exception("ingest_failed", document_id=document_id)
        message = f"{type(exc).__name__}: {exc}"[:900]
        try:
            _set_status(session, doc_uuid, "failed", error=message)
            session.execute(
                update(IngestionJob).where(IngestionJob.id == job_uuid).values(
                    status="failed", error=message, attempt=attempt
                )
            )
            session.commit()
        finally:
            pass
        raise
    finally:
        session.close()


@celery_app.task(name="app.ingestion.tasks.purge_document")
def purge_document(document_id: str) -> dict[str, Any]:
    """Delete every chunk of a document from the index. Called on document delete."""
    client = _os_client()
    res = client.delete_by_query(
        index=settings.opensearch.documents_index,
        body={"query": {"term": {"document_id": document_id}}},
        refresh=True,
    )
    return {"deleted": res.get("deleted", 0)}
