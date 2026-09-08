"""
Celery worker tasks for ingestion service.
Imports and re-exports tasks from app.ingestion.tasks for cleaner organization.
"""
from app.ingestion.tasks import ingest_document, purge_document

__all__ = ["ingest_document", "purge_document"]
