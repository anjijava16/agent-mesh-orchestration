"""The breaker and retry logic is the part most worth testing: it only runs when
something is already going wrong, so a bug here surfaces at the worst moment."""
from __future__ import annotations

import asyncio

import pytest

from app.core.errors import CircuitOpenError
from app.core.resilience import BreakerState, CircuitBreaker, is_retryable, retry_async


@pytest.mark.asyncio
async def test_breaker_opens_after_threshold():
    breaker = CircuitBreaker("test.open", failure_threshold=3, reset_timeout=60)

    async def boom():
        raise ConnectionError("upstream down")

    for _ in range(3):
        with pytest.raises(ConnectionError):
            await breaker.call(boom)

    assert breaker.metrics.state is BreakerState.OPEN
    with pytest.raises(CircuitOpenError):
        await breaker.call(boom)
    assert breaker.metrics.total_short_circuits == 1


@pytest.mark.asyncio
async def test_breaker_half_open_recovers():
    breaker = CircuitBreaker("test.recover", failure_threshold=2, success_threshold=2, reset_timeout=0.05)

    async def boom():
        raise ConnectionError("down")

    async def fine():
        return "ok"

    for _ in range(2):
        with pytest.raises(ConnectionError):
            await breaker.call(boom)
    assert breaker.metrics.state is BreakerState.OPEN

    await asyncio.sleep(0.06)
    assert await breaker.call(fine) == "ok"      # promotes to half-open, probe passes
    assert await breaker.call(fine) == "ok"      # second success closes it
    assert breaker.metrics.state is BreakerState.CLOSED


@pytest.mark.asyncio
async def test_breaker_ignores_non_retryable_errors():
    """A 400 from the provider is our bug, not theirs. It must not trip the circuit."""
    breaker = CircuitBreaker("test.client-error", failure_threshold=2)

    async def bad_request():
        raise ValueError("malformed payload")

    for _ in range(5):
        with pytest.raises(ValueError):
            await breaker.call(bad_request)
    assert breaker.metrics.state is BreakerState.CLOSED


@pytest.mark.asyncio
async def test_retry_succeeds_on_third_attempt():
    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TimeoutError("slow")
        return "done"

    result = await retry_async(flaky, max_attempts=4, initial_backoff=0.01, jitter=0)
    assert result == "done"
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_retry_gives_up_on_non_retryable():
    attempts = {"n": 0}

    async def bad():
        attempts["n"] += 1
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await retry_async(bad, max_attempts=5, initial_backoff=0.01)
    assert attempts["n"] == 1


def test_retryable_classification_by_status_code():
    class Fake(Exception):
        status_code = 503

    class Client(Exception):
        status_code = 400

    assert is_retryable(Fake())
    assert not is_retryable(Client())
    assert is_retryable(TimeoutError())
