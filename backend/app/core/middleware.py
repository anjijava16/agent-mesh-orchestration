"""HTTP middleware: correlation ids, timing, error shaping, rate limiting."""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger, request_id_ctx, user_id_ctx

log = get_logger(__name__)


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get(settings.request_id_header)
        rid = incoming or str(uuid.uuid4())
        request.state.request_id = rid
        request_id_ctx.set(rid)
        user_id_ctx.set(request.headers.get("X-User-ID"))

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except AppError as exc:
            log.warning("app_error", code=exc.code, path=request.url.path, message=exc.message)
            response = JSONResponse(status_code=exc.status_code, content=exc.to_payload())
        except Exception as exc:
            log.exception("unhandled_error", path=request.url.path)
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "The server hit an unexpected error." if not settings.debug
                        else f"{type(exc).__name__}: {exc}",
                        "request_id": rid,
                    }
                },
            )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response.headers[settings.request_id_header] = rid
        response.headers["X-Response-Time-ms"] = str(elapsed_ms)

        # SSE responses log on open; their duration is not meaningful here.
        if not request.url.path.endswith("/stream"):
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=elapsed_ms,
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window limiter, per user.

    In-process on purpose for a single-node deployment. With more than one
    replica, move the window into Redis - the interface here does not change.
    """

    def __init__(self, app, *, limit: int = 120, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path.startswith(("/health", "/docs", "/openapi", "/metrics")):
            return await call_next(request)

        key = request.headers.get("X-User-ID") or (request.client.host if request.client else "anonymous")
        now = time.time()
        window = self._hits[key]
        while window and now - window[0] > self.window:
            window.popleft()

        if len(window) >= self.limit:
            retry_after = int(self.window - (now - window[0])) + 1
            log.warning("rate_limited", key=key, path=request.url.path)
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited",
                                   "message": f"Rate limit of {self.limit} requests per {self.window}s exceeded."}},
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)
        return await call_next(request)
