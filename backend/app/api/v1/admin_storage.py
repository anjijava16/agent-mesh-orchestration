"""Object storage (MinIO / S3) admin router.

Browse buckets, list and manage objects, get presigned URLs.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.storage.object_store import _client as s3_client

router = APIRouter(prefix="/admin/storage", tags=["admin-storage"])


def _s3() -> Any:
    return s3_client()


# ------------------------------------------------------------------ buckets
@router.get("/buckets")
async def list_buckets() -> dict:
    """List all buckets."""
    response = await asyncio.to_thread(lambda: _s3().list_buckets())
    buckets = [
        {"name": b["Name"], "created": b["CreationDate"].isoformat()}
        for b in response.get("Buckets", [])
    ]
    return {"buckets": buckets, "total": len(buckets), "active_bucket": settings.storage.bucket}


@router.get("/buckets/{bucket}/info")
async def bucket_info(bucket: str) -> dict:
    """Bucket existence check and basic info."""
    try:
        await asyncio.to_thread(lambda: _s3().head_bucket(Bucket=bucket))
        return {"bucket": bucket, "exists": True}
    except Exception as exc:
        return {"bucket": bucket, "exists": False, "error": str(exc)[:200]}


# ------------------------------------------------------------------ objects
@router.get("/objects")
async def list_objects(
    prefix: str = Query("", description="Key prefix filter"),
    bucket: str = Query(default=None, description="Bucket name (defaults to app bucket)"),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    """List objects in a bucket with optional prefix filter."""
    bucket = bucket or settings.storage.bucket
    kwargs: dict[str, Any] = {"Bucket": bucket, "MaxKeys": limit}
    if prefix:
        kwargs["Prefix"] = prefix

    response = await asyncio.to_thread(lambda: _s3().list_objects_v2(**kwargs))
    objects = [
        {
            "key": obj["Key"],
            "size_bytes": obj["Size"],
            "last_modified": obj["LastModified"].isoformat(),
            "storage_class": obj.get("StorageClass"),
        }
        for obj in response.get("Contents", [])
    ]
    return {
        "bucket": bucket,
        "prefix": prefix,
        "objects": objects,
        "count": len(objects),
        "is_truncated": response.get("IsTruncated", False),
    }


@router.get("/objects/{key:path}")
async def object_metadata(
    key: str,
    bucket: str = Query(default=None),
) -> dict:
    """Get object metadata (head)."""
    bucket = bucket or settings.storage.bucket
    try:
        head = await asyncio.to_thread(lambda: _s3().head_object(Bucket=bucket, Key=key))
        return {
            "key": key,
            "bucket": bucket,
            "content_type": head.get("ContentType"),
            "size_bytes": head.get("ContentLength"),
            "last_modified": head["LastModified"].isoformat() if head.get("LastModified") else None,
            "etag": head.get("ETag"),
            "metadata": head.get("Metadata", {}),
        }
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Object not found: {exc}") from exc


@router.get("/objects/{key:path}/presign")
async def presigned_url(
    key: str,
    bucket: str = Query(default=None),
    expires: int = Query(3600, ge=60, le=86400),
) -> dict:
    """Generate a presigned download URL."""
    bucket = bucket or settings.storage.bucket

    def _sign() -> str:
        return _s3().generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires
        )

    url = await asyncio.to_thread(_sign)
    return {"key": key, "url": url, "expires_seconds": expires}


@router.delete("/objects/{key:path}")
async def delete_object(
    key: str,
    bucket: str = Query(default=None),
) -> dict:
    """Delete an object."""
    bucket = bucket or settings.storage.bucket
    await asyncio.to_thread(lambda: _s3().delete_object(Bucket=bucket, Key=key))
    return {"key": key, "bucket": bucket, "deleted": True}


# ------------------------------------------------------------------ stats
@router.get("/stats")
async def storage_stats() -> dict:
    """Storage configuration and summary."""
    bucket = settings.storage.bucket

    # Count objects
    total_objects = 0
    total_size = 0
    kwargs: dict[str, Any] = {"Bucket": bucket}
    try:
        while True:
            response = await asyncio.to_thread(lambda: _s3().list_objects_v2(**kwargs))
            for obj in response.get("Contents", []):
                total_objects += 1
                total_size += obj.get("Size", 0)
            if not response.get("IsTruncated"):
                break
            kwargs["ContinuationToken"] = response["NextContinuationToken"]
    except Exception:
        pass

    return {
        "backend": settings.storage.backend,
        "bucket": bucket,
        "endpoint_url": settings.storage.endpoint_url,
        "total_objects": total_objects,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "max_upload_mb": settings.storage.max_upload_bytes // (1024 * 1024),
    }
