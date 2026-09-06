"""FastAPI application entrypoint.

The lifespan handler is where every long-lived resource is created and torn
down. Nothing connects at import time - that is what lets the test suite import
this module without a database.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.core.middleware import CorrelationMiddleware, RateLimitMiddleware
from app.core.tracing import setup_tracing
from app.db.session import dispose_engine
from app.search.client import close_opensearch
from app.search.indices import ensure_indices

configure_logging(settings.log_level, settings.log_format)
setup_tracing()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("startup", app=settings.app_name, environment=settings.environment,
             framework_default=settings.agent.framework.value)

    # Dependency bootstrap is best-effort: a cold OpenSearch should not stop the
    # API from starting, because /health/ready is what gates traffic.
    try:
        await asyncio.wait_for(ensure_indices(), timeout=30)
    except Exception as exc:
        log.warning("opensearch_bootstrap_deferred", error=str(exc)[:300])

    try:
        from app.storage.object_store import ensure_bucket

        await asyncio.to_thread(ensure_bucket)
    except Exception as exc:
        log.warning("bucket_bootstrap_deferred", error=str(exc)[:300])

    yield

    log.info("shutdown")
    await close_opensearch()
    await dispose_engine()


app = FastAPI(
    title=f"{settings.app_name} API",
    description=(
        "Multi-agent orchestration over four interchangeable frameworks "
        "(Google ADK workflows, LangGraph, LangChain DeepAgents, Claude Agent SDK)."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(CorrelationMiddleware)
app.add_middleware(RateLimitMiddleware, limit=240, window_seconds=60)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[settings.request_id_header, "X-Response-Time-ms"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.exception_handler(AppError)
async def app_error_handler(_request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(RequestValidationError)
async def validation_handler(_request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error", "message": "Request body failed validation.",
                           "details": {"errors": exc.errors()[:10]}}},
    )


@app.get("/")
async def root() -> dict:
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "api": settings.api_prefix,
        "default_framework": settings.agent.framework.value,
    }
