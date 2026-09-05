"""Celery application.

Two queues on purpose:
  * ingest  - long, CPU-and-network heavy document work
  * default - short maintenance jobs

acks_late plus reject_on_worker_lost means a task that dies with its worker is
redelivered rather than lost. Combined with the idempotent indexer (chunk ids
are deterministic), a redelivery overwrites the same documents instead of
duplicating them.
"""
from __future__ import annotations

from celery import Celery
from kombu import Queue

from app.config import settings

celery_app = Celery(
    "agentmesh",
    broker=settings.redis.broker_url,
    backend=settings.redis.result_backend,
    include=["app.ingestion.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,          # long tasks: do not hoard
    worker_max_tasks_per_child=50,         # bound memory growth from parsers
    result_expires=86_400,
    task_soft_time_limit=settings.ingestion.task_soft_time_limit,
    task_time_limit=settings.ingestion.task_time_limit,
    task_default_queue="default",
    task_queues=(Queue("default"), Queue("ingest")),
    task_routes={"app.ingestion.tasks.ingest_document": {"queue": "ingest"}},
    broker_transport_options={"visibility_timeout": 3600},
)
