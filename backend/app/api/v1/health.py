"""Liveness, readiness and dependency health.

Three distinct endpoints because Kubernetes asks three different questions:
  /health/live   - is the process up? (never touches a dependency)
  /health/ready  - can it serve traffic? (touches every dependency)
  /health        - full detail for humans and dashboards
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.agents.registry import available_frameworks
from app.config import settings
from app.core.resilience import CircuitBreaker
from app.db.session import get_sessionmaker
from app.search.client import get_opensearch

router = APIRouter(tags=["health"])
VERSION = "1.0.0"


async def _check_postgres() -> dict[str, Any]:
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "up"}
    except Exception as exc:
        return {"status": "down", "error": str(exc)[:200]}


async def _check_opensearch() -> dict[str, Any]:
    try:
        info = await get_opensearch().cluster.health()
        return {"status": "up", "cluster_status": info.get("status")}
    except Exception as exc:
        return {"status": "down", "error": str(exc)[:200]}


async def _check_redis() -> dict[str, Any]:
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis.url)
        await client.ping()
        await client.aclose()
        return {"status": "up"}
    except Exception as exc:
        return {"status": "down", "error": str(exc)[:200]}


async def _check_storage() -> dict[str, Any]:
    try:
        from app.storage.object_store import _client

        await asyncio.to_thread(lambda: _client().head_bucket(Bucket=settings.storage.bucket))
        return {"status": "up", "backend": settings.storage.backend}
    except Exception as exc:
        return {"status": "down", "error": str(exc)[:200]}


@router.get("/health/live")
async def live() -> dict:
    return {"status": "alive", "version": VERSION}


@router.get("/health/ready")
async def ready(response: Response) -> dict:
    checks = await asyncio.gather(_check_postgres(), _check_opensearch(), _check_redis())
    names = ("postgres", "opensearch", "redis")
    payload = dict(zip(names, checks, strict=True))
    healthy = all(c["status"] == "up" for c in checks)
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if healthy else "degraded", "dependencies": payload}


@router.get("/health")
async def health() -> dict:
    checks = await asyncio.gather(_check_postgres(), _check_opensearch(), _check_redis(), _check_storage())
    names = ("postgres", "opensearch", "redis", "object_storage")
    dependencies = dict(zip(names, checks, strict=True))
    breakers = CircuitBreaker.snapshot()
    degraded = any(c["status"] == "down" for c in checks) or any(
        b["state"] == "open" for b in breakers.values()
    )
    return {
        "status": "degraded" if degraded else "healthy",
        "version": VERSION,
        "environment": settings.environment,
        "dependencies": dependencies,
        "breakers": breakers,
        "frameworks": available_frameworks(),
    }
