"""Per-endpoint rate limiting using slowapi.

slowapi wraps limits (a well-known Python rate-limiting library) and integrates
it with FastAPI/Starlette.  It gives us per-endpoint limits declared as
decorators, which is more granular than the existing blanket middleware.

The custom RateLimitMiddleware in middleware.py remains as a global safety net
(all endpoints, same bucket).  slowapi adds fine-grained control: chat
endpoints get a tighter limit than read-only endpoints, file uploads get their
own budget, etc.

Usage in a router module::

    from app.core.rate_limit import limiter

    @router.post("/chat/stream")
    @limiter.limit("20/minute")
    async def chat_stream(request: Request, ...):
        ...
"""
from __future__ import annotations

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _key_func(request: Request) -> str:
    """Rate-limit key: prefer the authenticated user id, fall back to IP."""
    return (
        request.headers.get("X-User-ID")
        or (request.client.host if request.client else None)
        or get_remote_address(request)
    )


# Global limiter — attach to app.state in main.py so slowapi can find it.
limiter = Limiter(
    key_func=_key_func,
    default_limits=[f"{settings.resilience.rate_limit_default}/minute"],
    storage_uri="memory://",  # single-node; swap to redis:// for multi-replica
    strategy="fixed-window",  # Valid strategies: fixed-window, moving-window, fixed-window-elastic-expiry (requires limits>=2.0)
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Return a JSON 429 matching the AppError format used everywhere else."""
    log.warning("slowapi_rate_limited", key=_key_func(request), path=request.url.path,
                detail=str(exc.detail)[:200])
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limited",
                "message": f"Rate limit exceeded: {exc.detail}",
            }
        },
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
    )
