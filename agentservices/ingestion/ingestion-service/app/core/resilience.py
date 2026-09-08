"""Retry, circuit breaker, timeout and bulkhead primitives.

Deliberately dependency-light (no third-party breaker) because we need:
  * async-native behaviour,
  * per-dependency state that we can expose over /health and /metrics,
  * the half-open probe semantics that most small libraries get wrong.

Usage:

    breaker = CircuitBreaker("anthropic")

    @with_resilience(breaker=breaker, timeout=60)
    async def call_model(...): ...
"""
from __future__ import annotations

import asyncio
import functools
import random
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

from app.config import settings
from app.core.errors import CircuitOpenError, UpstreamError
from app.core.logging import get_logger

log = get_logger(__name__)
T = TypeVar("T")


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# Errors that are worth retrying. Anything else (a 400, a schema error) fails fast.
RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,
    OSError,
    UpstreamError,
)


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, CircuitOpenError):
        return False
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return True
    # Provider SDKs raise their own classes; match on shape rather than import
    # them all and couple ourselves to every vendor package.
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int) and (status == 408 or status == 429 or 500 <= status < 600):
        return True
    name = type(exc).__name__.lower()
    return any(token in name for token in ("timeout", "unavailable", "overloaded", "ratelimit", "connection"))


@dataclass
class BreakerMetrics:
    state: BreakerState = BreakerState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_calls: int = 0
    total_failures: int = 0
    total_short_circuits: int = 0
    opened_at: float | None = None
    last_error: str | None = None


class CircuitBreaker:
    """Classic three-state breaker.

    CLOSED     -> normal traffic; count consecutive failures.
    OPEN       -> reject immediately until reset_timeout elapses.
    HALF_OPEN  -> allow a small number of probe calls; promote or demote.
    """

    _registry: dict[str, CircuitBreaker] = {}

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int | None = None,
        success_threshold: int | None = None,
        reset_timeout: float | None = None,
        half_open_max_calls: int | None = None,
    ) -> None:
        cfg = settings.resilience
        self.name = name
        self.failure_threshold = failure_threshold or cfg.failure_threshold
        self.success_threshold = success_threshold or cfg.success_threshold
        self.reset_timeout = reset_timeout or cfg.breaker_reset_timeout_seconds
        self.half_open_max_calls = half_open_max_calls or cfg.half_open_max_calls

        self.metrics = BreakerMetrics()
        self._lock = asyncio.Lock()
        self._half_open_inflight = 0
        CircuitBreaker._registry[name] = self

    # -- introspection -------------------------------------------------
    @classmethod
    def registry(cls) -> dict[str, CircuitBreaker]:
        return dict(cls._registry)

    @classmethod
    def snapshot(cls) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "state": b.metrics.state.value,
                "consecutive_failures": b.metrics.consecutive_failures,
                "total_calls": b.metrics.total_calls,
                "total_failures": b.metrics.total_failures,
                "total_short_circuits": b.metrics.total_short_circuits,
                "last_error": b.metrics.last_error,
                "opened_for_seconds": (time.monotonic() - b.metrics.opened_at) if b.metrics.opened_at else None,
            }
            for name, b in cls._registry.items()
        }

    # -- gate ----------------------------------------------------------
    async def _before_call(self) -> None:
        async with self._lock:
            m = self.metrics
            if m.state is BreakerState.OPEN:
                assert m.opened_at is not None
                if (time.monotonic() - m.opened_at) >= self.reset_timeout:
                    m.state = BreakerState.HALF_OPEN
                    m.consecutive_successes = 0
                    self._half_open_inflight = 0
                    log.info("circuit_half_open", breaker=self.name)
                else:
                    m.total_short_circuits += 1
                    raise CircuitOpenError(
                        f"Circuit '{self.name}' is open; refusing call.",
                        details={"breaker": self.name, "retry_after_seconds": round(
                            self.reset_timeout - (time.monotonic() - m.opened_at), 2)},
                    )

            if m.state is BreakerState.HALF_OPEN:
                if self._half_open_inflight >= self.half_open_max_calls:
                    m.total_short_circuits += 1
                    raise CircuitOpenError(
                        f"Circuit '{self.name}' is half-open and saturated with probes.",
                        details={"breaker": self.name},
                    )
                self._half_open_inflight += 1

            m.total_calls += 1

    async def _on_success(self) -> None:
        async with self._lock:
            m = self.metrics
            m.consecutive_failures = 0
            if m.state is BreakerState.HALF_OPEN:
                self._half_open_inflight = max(0, self._half_open_inflight - 1)
                m.consecutive_successes += 1
                if m.consecutive_successes >= self.success_threshold:
                    m.state = BreakerState.CLOSED
                    m.opened_at = None
                    log.info("circuit_closed", breaker=self.name)

    async def _on_failure(self, exc: BaseException) -> None:
        async with self._lock:
            m = self.metrics
            m.total_failures += 1
            m.last_error = f"{type(exc).__name__}: {exc}"[:500]
            if m.state is BreakerState.HALF_OPEN:
                self._half_open_inflight = max(0, self._half_open_inflight - 1)
                m.state = BreakerState.OPEN
                m.opened_at = time.monotonic()
                log.warning("circuit_reopened", breaker=self.name, error=m.last_error)
                return
            m.consecutive_failures += 1
            if m.consecutive_failures >= self.failure_threshold:
                m.state = BreakerState.OPEN
                m.opened_at = time.monotonic()
                log.warning("circuit_opened", breaker=self.name, failures=m.consecutive_failures, error=m.last_error)

    async def call(self, fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        await self._before_call()
        try:
            result = await fn(*args, **kwargs)
        except BaseException as exc:
            # Only dependency-shaped failures should trip the breaker. A bad
            # user payload is not a reason to stop calling the provider.
            if is_retryable(exc):
                await self._on_failure(exc)
            else:
                await self._on_success()
            raise
        await self._on_success()
        return result


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int | None = None,
    initial_backoff: float | None = None,
    max_backoff: float | None = None,
    multiplier: float | None = None,
    jitter: float | None = None,
    retry_on: Callable[[BaseException], bool] = is_retryable,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
    label: str = "operation",
) -> T:
    """Exponential backoff with full jitter."""
    cfg = settings.resilience
    max_attempts = max_attempts or cfg.max_attempts
    backoff = initial_backoff or cfg.initial_backoff_seconds
    max_backoff = max_backoff or cfg.max_backoff_seconds
    multiplier = multiplier or cfg.backoff_multiplier
    jitter = cfg.jitter_seconds if jitter is None else jitter

    last: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except BaseException as exc:
            last = exc
            if attempt >= max_attempts or not retry_on(exc):
                raise
            delay = min(backoff * (multiplier ** (attempt - 1)), max_backoff)
            delay += random.uniform(0, jitter)
            if on_retry:
                on_retry(attempt, exc, delay)
            log.warning(
                "retrying",
                label=label,
                attempt=attempt,
                max_attempts=max_attempts,
                sleep_seconds=round(delay, 3),
                error=f"{type(exc).__name__}: {exc}"[:300],
            )
            await asyncio.sleep(delay)
    assert last is not None
    raise last


def with_resilience(
    *,
    breaker: CircuitBreaker | None = None,
    timeout: float | None = None,
    max_attempts: int | None = None,
    label: str | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Compose timeout -> breaker -> retry around an async callable.

    Order matters. The timeout is innermost so each attempt gets its own budget;
    the breaker sits inside the retry loop so a tripped circuit is observed by
    every attempt rather than being retried around.
    """

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        name = label or fn.__qualname__

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            async def attempt() -> T:
                async def guarded() -> T:
                    if timeout:
                        return await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout)
                    return await fn(*args, **kwargs)

                if breaker:
                    return await breaker.call(guarded)
                return await guarded()

            return await retry_async(attempt, max_attempts=max_attempts, label=name)

        return wrapper

    return decorator


@dataclass
class Bulkhead:
    """Cap concurrency per dependency so one slow provider cannot exhaust the loop."""

    name: str
    limit: int = 16
    _sem: asyncio.Semaphore = field(init=False)

    def __post_init__(self) -> None:
        self._sem = asyncio.Semaphore(self.limit)

    async def run(self, fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        async with self._sem:
            return await fn(*args, **kwargs)


# Shared breakers - one per external dependency, named for the /health payload.
LLM_BREAKERS: dict[str, CircuitBreaker] = {
    "openai": CircuitBreaker("llm.openai"),
    "anthropic": CircuitBreaker("llm.anthropic"),
    "google": CircuitBreaker("llm.google"),
}
OPENSEARCH_BREAKER = CircuitBreaker("opensearch")
STORAGE_BREAKER = CircuitBreaker("object_storage")
EMBEDDING_BREAKER = CircuitBreaker("embeddings")
TOOL_BREAKERS: dict[str, CircuitBreaker] = {}


def tool_breaker(tool_name: str) -> CircuitBreaker:
    if tool_name not in TOOL_BREAKERS:
        TOOL_BREAKERS[tool_name] = CircuitBreaker(f"tool.{tool_name}")
    return TOOL_BREAKERS[tool_name]


def all_breaker_names() -> Iterable[str]:
    return CircuitBreaker.registry().keys()
