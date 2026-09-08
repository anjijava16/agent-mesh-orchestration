"""S3 / MinIO object storage.

boto3 is sync, so every call goes through a thread. The alternative (aioboto3)
adds a dependency for a code path that is not on the hot loop - uploads are
already IO-bound and bounded by the client's connection.
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import settings
from app.core.errors import UpstreamError
from app.core.logging import get_logger
from app.core.resilience import STORAGE_BREAKER, with_resilience

log = get_logger(__name__)


def _client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.storage.endpoint_url,
        aws_access_key_id=settings.storage.access_key,
        aws_secret_access_key=settings.storage.secret_key,
        region_name=settings.storage.region,
        config=BotoConfig(retries={"max_attempts": 0}, signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    client = _client()
    bucket = settings.storage.bucket
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        try:
            client.create_bucket(Bucket=bucket)
            log.info("bucket_created", bucket=bucket)
        except ClientError as exc:  # pragma: no cover
            log.error("bucket_create_failed", bucket=bucket, error=str(exc))


class ObjectStore:
    def __init__(self) -> None:
        self.bucket = settings.storage.bucket

    @with_resilience(breaker=STORAGE_BREAKER, timeout=120, label="storage.put")
    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        def _put() -> None:
            _client().put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

        await asyncio.to_thread(_put)
        return key

    @with_resilience(breaker=STORAGE_BREAKER, timeout=120, label="storage.get")
    async def get(self, key: str) -> bytes:
        def _get() -> bytes:
            return _client().get_object(Bucket=self.bucket, Key=key)["Body"].read()

        try:
            return await asyncio.to_thread(_get)
        except ClientError as exc:
            raise UpstreamError(f"Object {key} could not be read", details={"error": str(exc)}) from exc

    def get_sync(self, key: str) -> bytes:
        """Celery path."""
        return _client().get_object(Bucket=self.bucket, Key=key)["Body"].read()

    @with_resilience(breaker=STORAGE_BREAKER, timeout=30, label="storage.delete")
    async def delete(self, key: str) -> None:
        await asyncio.to_thread(lambda: _client().delete_object(Bucket=self.bucket, Key=key))

    async def presigned_url(self, key: str, expires: int | None = None) -> str:
        expires = expires or settings.storage.presign_expiry_seconds

        def _sign() -> str:
            return _client().generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
            )

        return await asyncio.to_thread(_sign)


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_store: ObjectStore | None = None


def get_object_store() -> ObjectStore:
    global _store
    if _store is None:
        _store = ObjectStore()
    return _store
