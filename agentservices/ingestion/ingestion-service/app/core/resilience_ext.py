"""Industry-standard resilience primitives using tenacity + pybreaker.

This module provides production-grade retry and circuit breaker patterns using
well-known libraries, configured from ResilienceSettings:

    tenacity   -- declarative retry policies with exponential backoff, jitter
                  and per-exception filtering.
    pybreaker  -- thread/async-safe circuit breakers with three-state
                  (closed / open / half-open) semantics.

The existing custom primitives in ``resilience.py`` remain available; this
module offers the same guarantees through standard libraries that ops teams
already know how to monitor and configure.

Usage::

    from app.core.resilience_ext import pb_llm_breakers, tenacity_retry

    @tenacity_retry(label="llm.invoke")
    async def call_llm(...):
        async with pb_llm_breakers["openai"]:
            return await client.chat(...)

    # Or use the combined decorator:
    from app.core.resilience_ext import with_tenacity_resilience

    @with_tenacity_resilience(breaker_name="openai", timeout=120)
    async def guarded_call(...):
        ...
"""
from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import pybreaker
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    after_log,
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.config import settings
from app.core.errors import CircuitOpenError, UpstreamError
from app.core.logging import get_logger

log = get_logger(__name__)
_tenacity_logger = logging.getLogger("tenacity.resilience")
T = TypeVar("T")


# ---------------------------------------------------------------------------
# Retryable exception classification (reuses the same logic as resilience.py)
# ---------------------------------------------------------------------------

def _is_retryable(exc: BaseException) -> bool:
    """Decide whether an exception is worth retrying.

    Mirrors ``resilience.is_retryable`` so both modules agree on what is
    transient.  Non-retryable errors (bad payloads, auth failures, circuit
    open) fail fast.
    """
    if isinstance(exc, (CircuitOpenError, pybreaker.CircuitBreakerError)):
        return False
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError, UpstreamError)):
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int) and (status == 408 or status == 429 or 500 <= status < 600):
        return True
    name = type(exc).__name__.lower()
    return any(tok in name for tok in ("timeout", "unavailable", "overloaded", "ratelimit", "connection"))


# ---------------------------------------------------------------------------
# Tenacity retry factory
# ---------------------------------------------------------------------------

def tenacity_retry(
    *,
    max_attempts: int | None = None,
    initial_backoff: float | None = None,
    max_backoff: float | None = None,
    jitter: float | None = None,
    label: str = "operation",
) -> Callable:
    """Build a tenacity ``@retry`` decorator pre-configured from settings.

    Parameters mirror ``ResilienceSettings`` and default to its values when
    omitted, so callers only override what differs.
    """
    cfg = settings.resilience
    _max = max_attempts or cfg.max_attempts
    _init = initial_backoff or cfg.initial_backoff_seconds
    _cap = max_backoff or cfg.max_backoff_seconds
    _jit = jitter if jitter is not None else cfg.jitter_seconds

    return retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(_max),
        wait=wait_exponential_jitter(initial=_init, max=_cap, jitter=_jit),
        before_sleep=before_sleep_log(_tenacity_logger, logging.WARNING),
        reraise=True,
    )


# ---------------------------------------------------------------------------
# Pybreaker circuit breakers
# ---------------------------------------------------------------------------

class _PybreakerListener(pybreaker.CircuitBreakerListener):
    """Log state transitions so they appear in structured logs."""

    def state_change(self, cb: pybreaker.CircuitBreaker, old_state: Any, new_state: Any) -> None:
        log.info(
            "pybreaker_state_change",
            breaker=cb.name,
            old_state=str(old_state),
            new_state=str(new_state),
        )

    def failure(self, cb: pybreaker.CircuitBreaker, exc: Exception) -> None:
        log.warning(
            "pybreaker_failure",
            breaker=cb.name,
            error=f"{type(exc).__name__}: {exc}"[:300],
        )


_listener = _PybreakerListener()


def make_pybreaker(
    name: str,
    *,
    fail_max: int | None = None,
    reset_timeout: float | None = None,
    exclude: list[type[Exception]] | None = None,
) -> pybreaker.CircuitBreaker:
    """Create a pybreaker CircuitBreaker configured from ResilienceSettings."""
    cfg = settings.resilience
    return pybreaker.CircuitBreaker(
        name=name,
        fail_max=fail_max or cfg.failure_threshold,
        reset_timeout=reset_timeout or cfg.breaker_reset_timeout_seconds,
        exclude=[ValueError, TypeError, KeyError] + (exclude or []),
        listeners=[_listener],
    )


# Shared pybreaker instances -- one per external dependency.
pb_llm_breakers: dict[str, pybreaker.CircuitBreaker] = {
    "openai": make_pybreaker("pb.llm.openai"),
    "anthropic": make_pybreaker("pb.llm.anthropic"),
    "google": make_pybreaker("pb.llm.google"),
}
pb_opensearch_breaker = make_pybreaker("pb.opensearch")
pb_storage_breaker = make_pybreaker("pb.object_storage")
pb_embedding_breaker = make_pybreaker("pb.embeddings")

_PB_TOOL_BREAKERS: dict[str, pybreaker.CircuitBreaker] = {}


def pb_tool_breaker(tool_name: str) -> pybreaker.CircuitBreaker:
    """Get or create a pybreaker instance for a named tool."""
    if tool_name not in _PB_TOOL_BREAKERS:
        _PB_TOOL_BREAKERS[tool_name] = make_pybreaker(f"pb.tool.{tool_name}")
    return _PB_TOOL_BREAKERS[tool_name]


def pybreaker_snapshot() -> dict[str, dict[str, Any]]:
    """Gather state from every pybreaker instance for the /health endpoint."""
    all_breakers: dict[str, pybreaker.CircuitBreaker] = {
        **pb_llm_breakers,
        "opensearch": pb_opensearch_breaker,
        "object_storage": pb_storage_breaker,
        "embeddings": pb_embedding_breaker,
        **_PB_TOOL_BREAKERS,
    }
    return {
        name: {
            "state": cb.current_state,
            "fail_count": cb.fail_counter,
            "fail_max": cb.fail_max,
            "reset_timeout": cb.reset_timeout,
        }
        for name, cb in all_breakers.items()
    }


# ---------------------------------------------------------------------------
# Combined decorator: tenacity retry + pybreaker breaker + timeout
# ---------------------------------------------------------------------------

def with_tenacity_resilience(
    *,
    breaker_name: str | None = None,
    breaker: pybreaker.CircuitBreaker | None = None,
    timeout: float | None = None,
    max_attempts: int | None = None,
    label: str | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Compose tenacity retry + pybreaker circuit breaker + asyncio timeout.

    Layering order (outermost first):
        tenacity retry  ->  pybreaker gate  ->  asyncio.wait_for timeout

    This means each retry attempt independently checks the breaker and gets
    its own timeout budget.
    """
    cfg = settings.resilience
    _max = max_attempts or cfg.max_attempts
    _init = cfg.initial_backoff_seconds
    _cap = cfg.max_backoff_seconds
    _jit = cfg.jitter_seconds

    # Resolve breaker from name or direct instance.
    _breaker: pybreaker.CircuitBreaker | None = breaker
    if _breaker is None and breaker_name:
        _breaker = pb_llm_breakers.get(breaker_name) or make_pybreaker(breaker_name)

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        fn_label = label or fn.__qualname__

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_is_retryable),
                stop=stop_after_attempt(_max),
                wait=wait_exponential_jitter(initial=_init, max=_cap, jitter=_jit),
                before_sleep=_log_retry(fn_label),
                reraise=True,
            ):
                with attempt:
                    # Pybreaker gate
                    if _breaker is not None:
                        try:
                            _breaker.call(lambda: None)  # sync gate check
                        except pybreaker.CircuitBreakerError:
                            raise CircuitOpenError(
                                f"Pybreaker '{_breaker.name}' is open; refusing call.",
                                details={"breaker": _breaker.name},
                            )

                    # Timeout + actual call
                    try:
                        if timeout:
                            result = await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout)
                        else:
                            result = await fn(*args, **kwargs)
                    except Exception as exc:
                        if _breaker is not None and _is_retryable(exc):
                            # Record failure in pybreaker
                            try:
                                _breaker.call(lambda: (_ for _ in ()).throw(exc))
                            except (pybreaker.CircuitBreakerError, type(exc)):
                                pass
                        raise

                    # Record success in pybreaker
                    if _breaker is not None:
                        try:
                            _breaker.call(lambda: None)
                        except pybreaker.CircuitBreakerError:
                            pass
                    return result

            # Should never reach here, but satisfy the type checker.
            raise RuntimeError("Retry loop exited unexpectedly")

        return wrapper

    return decorator


def _log_retry(label: str) -> Callable[[RetryCallState], None]:
    """Return a tenacity before_sleep callback that logs with structlog."""

    def _before_sleep(retry_state: RetryCallState) -> None:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        log.warning(
            "tenacity_retrying",
            label=label,
            attempt=retry_state.attempt_number,
            wait=round(retry_state.next_action.sleep if retry_state.next_action else 0, 3),  # type: ignore[union-attr]
            error=f"{type(exc).__name__}: {exc}"[:300] if exc else "unknown",
        )

    return _before_sleep
