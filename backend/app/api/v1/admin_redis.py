"""Redis admin router.

Server info, key browsing, and basic get/set/delete for debugging cache and
queue state.
"""
from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/admin/redis", tags=["admin-redis"])


def _client(db: int | None = None) -> aioredis.Redis:
    url = f"redis://{settings.redis.host}:{settings.redis.port}/{db if db is not None else settings.redis.db}"
    return aioredis.from_url(url, decode_responses=True)


class SetKeyBody(BaseModel):
    value: str
    ttl_seconds: int | None = None


# ------------------------------------------------------------------ info
@router.get("/info")
async def server_info() -> dict:
    """Redis server info summary."""
    client = _client()
    try:
        info = await client.info()
        return {
            "version": info.get("redis_version"),
            "uptime_seconds": info.get("uptime_in_seconds"),
            "connected_clients": info.get("connected_clients"),
            "used_memory_human": info.get("used_memory_human"),
            "used_memory_bytes": info.get("used_memory"),
            "total_commands_processed": info.get("total_commands_processed"),
            "keyspace": info.get("db0", {}),
            "role": info.get("role"),
        }
    finally:
        await client.aclose()


@router.get("/databases")
async def database_info() -> dict:
    """Key counts across all Redis databases used by the app."""
    out = {}
    for name, db_num in [
        ("app", settings.redis.db),
        ("celery_broker", settings.redis.celery_broker_db),
        ("celery_results", settings.redis.celery_result_db),
    ]:
        client = _client(db_num)
        try:
            size = await client.dbsize()
            out[name] = {"db": db_num, "key_count": size}
        except Exception as exc:
            out[name] = {"db": db_num, "error": str(exc)[:200]}
        finally:
            await client.aclose()
    return out


# ------------------------------------------------------------------ keys
@router.get("/keys")
async def list_keys(
    pattern: str = Query("*", description="Glob pattern"),
    db: int = Query(0, ge=0, le=15),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    """Scan keys matching a pattern."""
    client = _client(db)
    try:
        keys: list[str] = []
        async for key in client.scan_iter(match=pattern, count=limit):
            keys.append(key)
            if len(keys) >= limit:
                break
        return {"pattern": pattern, "db": db, "keys": keys, "count": len(keys)}
    finally:
        await client.aclose()


@router.get("/keys/{key:path}")
async def get_key(key: str, db: int = Query(0, ge=0, le=15)) -> dict:
    """Get the value and metadata of a key."""
    client = _client(db)
    try:
        key_type = await client.type(key)
        ttl = await client.ttl(key)

        if key_type == "string":
            value = await client.get(key)
        elif key_type == "list":
            value = await client.lrange(key, 0, 99)
        elif key_type == "set":
            value = list(await client.smembers(key))
        elif key_type == "zset":
            value = await client.zrange(key, 0, 99, withscores=True)
        elif key_type == "hash":
            value = await client.hgetall(key)
        elif key_type == "none":
            raise HTTPException(status_code=404, detail=f"Key '{key}' not found")
        else:
            value = f"<unsupported type: {key_type}>"

        return {"key": key, "type": key_type, "ttl": ttl, "value": value}
    finally:
        await client.aclose()


@router.put("/keys/{key:path}")
async def set_key(key: str, body: SetKeyBody, db: int = Query(0, ge=0, le=15)) -> dict:
    """Set a string key."""
    client = _client(db)
    try:
        await client.set(key, body.value, ex=body.ttl_seconds)
        return {"key": key, "value": body.value, "ttl": body.ttl_seconds}
    finally:
        await client.aclose()


@router.delete("/keys/{key:path}")
async def delete_key(key: str, db: int = Query(0, ge=0, le=15)) -> dict:
    """Delete a key."""
    client = _client(db)
    try:
        deleted = await client.delete(key)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Key '{key}' not found")
        return {"key": key, "deleted": True}
    finally:
        await client.aclose()


# ------------------------------------------------------------------ queue inspect
@router.get("/queues")
async def celery_queue_lengths() -> dict:
    """Length of Celery task queues in the broker database."""
    client = _client(settings.redis.celery_broker_db)
    try:
        queues = {}
        for q in ["default", "ingest", "celery"]:
            length = await client.llen(q)
            queues[q] = length
        return {"queues": queues}
    finally:
        await client.aclose()
