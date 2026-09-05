"""Celery admin router.

Worker status, active/reserved/scheduled tasks, task results, and queue control.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.ingestion.celery_app import celery_app

router = APIRouter(prefix="/admin/celery", tags=["admin-celery"])


def _inspect_sync(method: str) -> dict[str, Any] | None:
    """Run a celery inspect command synchronously (called via to_thread)."""
    inspector = celery_app.control.inspect(timeout=5)
    return getattr(inspector, method)()


# ------------------------------------------------------------------ workers
@router.get("/workers")
async def list_workers() -> dict:
    """List registered workers with their stats."""
    stats = await asyncio.to_thread(_inspect_sync, "stats")
    if not stats:
        return {"workers": [], "total": 0, "note": "No workers responded"}

    workers = []
    for name, info in stats.items():
        workers.append({
            "name": name,
            "pid": info.get("pid"),
            "concurrency": info.get("pool", {}).get("max-concurrency"),
            "prefetch_count": info.get("prefetch_count"),
            "total_tasks": info.get("total", {}),
            "uptime": info.get("clock"),
        })
    return {"workers": workers, "total": len(workers)}


@router.get("/workers/ping")
async def ping_workers() -> dict:
    """Ping all workers."""
    result = await asyncio.to_thread(lambda: celery_app.control.ping(timeout=5))
    return {"responses": result or []}


# ------------------------------------------------------------------ tasks
@router.get("/tasks/active")
async def active_tasks() -> dict:
    """Tasks currently being executed."""
    result = await asyncio.to_thread(_inspect_sync, "active")
    return {"active": result or {}}


@router.get("/tasks/reserved")
async def reserved_tasks() -> dict:
    """Tasks that have been received but not yet started."""
    result = await asyncio.to_thread(_inspect_sync, "reserved")
    return {"reserved": result or {}}


@router.get("/tasks/scheduled")
async def scheduled_tasks() -> dict:
    """Tasks waiting for their ETA."""
    result = await asyncio.to_thread(_inspect_sync, "scheduled")
    return {"scheduled": result or {}}


@router.get("/tasks/registered")
async def registered_tasks() -> dict:
    """All task names registered with the workers."""
    result = await asyncio.to_thread(_inspect_sync, "registered")
    return {"registered": result or {}}


@router.get("/tasks/{task_id}")
async def get_task_result(task_id: str) -> dict:
    """Fetch the result/status of a specific task by ID."""
    result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": str(result.result)[:2000] if result.result else None,
        "date_done": str(result.date_done) if result.date_done else None,
        "traceback": result.traceback[:2000] if result.traceback else None,
    }


# ------------------------------------------------------------------ control
@router.post("/tasks/{task_id}/revoke")
async def revoke_task(task_id: str, terminate: bool = Query(False)) -> dict:
    """Revoke a pending or running task."""
    celery_app.control.revoke(task_id, terminate=terminate, signal="SIGTERM")
    return {"task_id": task_id, "revoked": True, "terminated": terminate}


@router.post("/purge")
async def purge_queues() -> dict:
    """Purge all pending tasks from all queues."""
    count = celery_app.control.purge()
    return {"purged": count or 0}


# ------------------------------------------------------------------ queue config
@router.get("/config")
async def celery_config() -> dict:
    """Current Celery configuration (safe subset)."""
    conf = celery_app.conf
    return {
        "broker_url": str(conf.broker_url).replace("//", "//***:***@") if conf.broker_url else None,
        "result_backend": str(conf.result_backend).replace("//", "//***:***@") if conf.result_backend else None,
        "task_serializer": conf.task_serializer,
        "timezone": conf.timezone,
        "task_acks_late": conf.task_acks_late,
        "worker_prefetch_multiplier": conf.worker_prefetch_multiplier,
        "worker_max_tasks_per_child": conf.worker_max_tasks_per_child,
        "task_soft_time_limit": conf.task_soft_time_limit,
        "task_time_limit": conf.task_time_limit,
        "task_default_queue": conf.task_default_queue,
        "task_queues": [q.name for q in (conf.task_queues or [])],
    }
