"""Metrics and system diagnostics router.

Aggregates circuit breaker state, connection pool stats, runtime info,
and dependency health into a single admin surface.
"""
from __future__ import annotations

import asyncio
import os
import platform
import sys
import time
from typing import Any

from fastapi import APIRouter

from app.config import settings
from app.core.resilience import CircuitBreaker
from app.db.session import get_engine

router = APIRouter(prefix="/admin/metrics", tags=["admin-metrics"])

_startup_time = time.time()


# ------------------------------------------------------------------ overview
@router.get("/overview")
async def overview() -> dict:
    """System overview: runtime, uptime, config summary."""
    return {
        "app_name": settings.app_name,
        "environment": settings.environment,
        "python_version": sys.version,
        "platform": platform.platform(),
        "pid": os.getpid(),
        "uptime_seconds": round(time.time() - _startup_time, 1),
        "default_framework": settings.agent.framework.value,
        "default_provider": settings.agent.provider.value,
        "default_model": settings.agent.model,
    }


# ------------------------------------------------------------------ breakers
@router.get("/breakers")
async def circuit_breakers() -> dict:
    """Current state of all circuit breakers."""
    snapshot = CircuitBreaker.snapshot()
    summary = {
        "total": len(snapshot),
        "open": sum(1 for b in snapshot.values() if b["state"] == "open"),
        "half_open": sum(1 for b in snapshot.values() if b["state"] == "half_open"),
        "closed": sum(1 for b in snapshot.values() if b["state"] == "closed"),
    }
    return {"summary": summary, "breakers": snapshot}


@router.post("/breakers/{name}/reset")
async def reset_breaker(name: str) -> dict:
    """Force-reset a circuit breaker to closed state."""
    registry = CircuitBreaker.registry()
    breaker = registry.get(name)
    if not breaker:
        return {"error": f"Breaker '{name}' not found", "available": list(registry.keys())}

    breaker.metrics.state = breaker.metrics.state.__class__("closed")
    breaker.metrics.consecutive_failures = 0
    breaker.metrics.opened_at = None
    return {"breaker": name, "state": "closed", "reset": True}


# ------------------------------------------------------------------ connections
@router.get("/connections")
async def connection_pools() -> dict:
    """Connection pool stats across all dependencies."""
    pools: dict[str, Any] = {}

    # Postgres
    try:
        engine = get_engine()
        pool = engine.pool
        pools["postgres"] = {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "total": pool.checkedin() + pool.checkedout(),
        }
    except Exception as exc:
        pools["postgres"] = {"error": str(exc)[:200]}

    # Redis
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis.url)
        info = await client.info("clients")
        pools["redis"] = {
            "connected_clients": info.get("connected_clients"),
            "blocked_clients": info.get("blocked_clients"),
        }
        await client.aclose()
    except Exception as exc:
        pools["redis"] = {"error": str(exc)[:200]}

    # OpenSearch
    try:
        from app.search.client import get_opensearch

        client = get_opensearch()
        health = await client.cluster.health()
        pools["opensearch"] = {
            "status": health.get("status"),
            "active_shards": health.get("active_shards"),
            "relocating_shards": health.get("relocating_shards"),
        }
    except Exception as exc:
        pools["opensearch"] = {"error": str(exc)[:200]}

    return pools


# ------------------------------------------------------------------ config (safe)
@router.get("/config")
async def safe_config() -> dict:
    """Non-secret configuration values for debugging."""
    return {
        "database": {
            "host": settings.database.host,
            "port": settings.database.port,
            "db": settings.database.db,
            "pool_size": settings.database.pool_size,
            "max_overflow": settings.database.max_overflow,
        },
        "opensearch": {
            "host": settings.opensearch.host,
            "port": settings.opensearch.port,
            "documents_index": settings.opensearch.documents_index,
            "memory_index": settings.opensearch.memory_index,
            "embedding_dim": settings.opensearch.embedding_dim,
        },
        "redis": {
            "host": settings.redis.host,
            "port": settings.redis.port,
            "app_db": settings.redis.db,
            "broker_db": settings.redis.celery_broker_db,
            "result_db": settings.redis.celery_result_db,
        },
        "storage": {
            "backend": settings.storage.backend,
            "bucket": settings.storage.bucket,
            "max_upload_mb": settings.storage.max_upload_bytes // (1024 * 1024),
        },
        "resilience": {
            "max_attempts": settings.resilience.max_attempts,
            "failure_threshold": settings.resilience.failure_threshold,
            "breaker_reset_timeout": settings.resilience.breaker_reset_timeout_seconds,
            "llm_timeout": settings.resilience.llm_timeout_seconds,
        },
        "agent": {
            "framework": settings.agent.framework.value,
            "provider": settings.agent.provider.value,
            "model": settings.agent.model,
            "temperature": settings.agent.temperature,
            "max_tokens": settings.agent.max_tokens,
            "max_orchestrator_steps": settings.agent.max_orchestrator_steps,
        },
        "ingestion": {
            "chunk_size": settings.ingestion.chunk_size,
            "chunk_overlap": settings.ingestion.chunk_overlap,
            "embedding_provider": settings.ingestion.embedding_provider.value,
            "embedding_model": settings.ingestion.embedding_model,
        },
        "api_keys_set": {
            "openai": bool(settings.openai_api_key),
            "anthropic": bool(settings.anthropic_api_key),
            "google": bool(settings.google_api_key),
        },
    }


# ------------------------------------------------------------------ dependencies
@router.get("/dependencies")
async def dependency_versions() -> dict:
    """Installed versions of key dependencies."""
    import importlib.metadata

    packages = [
        "fastapi", "sqlalchemy", "asyncpg", "opensearch-py",
        "celery", "redis", "boto3",
        "langchain", "langchain-core", "langgraph", "deepagents",
        "google-adk", "claude-agent-sdk", "anthropic", "openai",
        "pydantic", "structlog",
    ]
    versions = {}
    for pkg in packages:
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = "not installed"
    return {"dependencies": versions}
