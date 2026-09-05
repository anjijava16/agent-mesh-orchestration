from __future__ import annotations

from opensearchpy import AsyncOpenSearch

from app.config import settings

_client: AsyncOpenSearch | None = None


def get_opensearch() -> AsyncOpenSearch:
    global _client
    if _client is None:
        _client = AsyncOpenSearch(
            hosts=[{"host": settings.opensearch.host, "port": settings.opensearch.port}],
            http_auth=(settings.opensearch.user, settings.opensearch.password),
            use_ssl=settings.opensearch.use_ssl,
            verify_certs=settings.opensearch.verify_certs,
            ssl_show_warn=False,
            timeout=settings.opensearch.timeout_seconds,
            max_retries=0,          # retries are our own concern (see core.resilience)
            retry_on_timeout=False,
        )
    return _client


async def close_opensearch() -> None:
    global _client
    if _client is not None:
        await _client.close()
    _client = None
