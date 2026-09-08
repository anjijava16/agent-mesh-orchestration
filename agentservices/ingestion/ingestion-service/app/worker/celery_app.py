"""Celery application for ingestion tasks."""
from celery import Celery

from app.config import settings
from app.logging_config import configure_logging, get_logger

configure_logging(settings.log_level)
log = get_logger(__name__)

celery_app = Celery(
    "ingestion",
    broker=settings.redis.broker_url,
    backend=settings.redis.result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    task_routes={
        "app.worker.tasks.ingest_document": {"queue": "ingest"},
        "app.worker.tasks.purge_document": {"queue": "ingest"},
    },
)

log.info("celery_app_initialized", broker=settings.redis.broker_url)
