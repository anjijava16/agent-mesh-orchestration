# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies including Tesseract for OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl libpq-dev poppler-utils tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Install dependencies first (cached layer)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

# Run as non-root user
RUN useradd --create-home --uid 10004 ingestion && chown -R ingestion:ingestion /srv
USER ingestion

# Default: run Celery worker
CMD ["celery", "-A", "app.worker.celery_app", "worker", \
     "--loglevel=INFO", "--concurrency=2", "-Q", "ingest,default", \
     "--max-tasks-per-child=50"]
