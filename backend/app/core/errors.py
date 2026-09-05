"""Application error taxonomy.

Each error knows its HTTP status and a stable machine code so the UI can react
without string-matching messages.
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UpstreamError(AppError):
    """A dependency (LLM, OpenSearch, S3) failed after retries."""

    status_code = 502
    code = "upstream_error"


class CircuitOpenError(AppError):
    """The breaker refused the call before it was attempted."""

    status_code = 503
    code = "circuit_open"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class FrameworkNotAvailableError(AppError):
    status_code = 501
    code = "framework_unavailable"
