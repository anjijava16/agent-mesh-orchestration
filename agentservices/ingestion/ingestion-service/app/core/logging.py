"""Structured logging with request correlation.

Every log line carries request_id / conversation_id / framework when they are
known, which is what makes a multi-agent trace readable after the fact.
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
conversation_id_ctx: ContextVar[str | None] = ContextVar("conversation_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)


def _inject_context(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key, ctx in (
        ("request_id", request_id_ctx),
        ("conversation_id", conversation_id_ctx),
        ("user_id", user_id_ctx),
    ):
        value = ctx.get()
        if value:
            event_dict[key] = value
    return event_dict


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=getattr(logging, level.upper(), logging.INFO))

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _inject_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer() if fmt == "json" else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Quiet the noisy libraries; we want our own lines to stand out.
    for noisy in ("opensearch", "urllib3", "httpx", "botocore", "boto3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
