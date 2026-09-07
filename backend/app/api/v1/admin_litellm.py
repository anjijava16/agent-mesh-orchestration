"""LiteLLM proxy passthrough endpoints.

Talks to the LiteLLM container (the platform's model egress gateway) using the
master key. Provides visibility into the proxy without leaving the AgentMesh API:
list available models, check proxy health, and run a test chat completion.

These are admin/infrastructure endpoints — they do not affect how agents use
the proxy (that happens transparently in ``llm/registry.py``).
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/admin/litellm", tags=["admin: litellm"])


class ProxyChatRequest(BaseModel):
    model: str = Field(default_factory=lambda: settings.agent.model)
    messages: list[dict[str, Any]] = Field(
        default_factory=lambda: [{"role": "user", "content": "ping"}]
    )
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=128, ge=1, le=4096)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.litellm_master_key}"}


async def _proxy_request(method: str, path: str, json: dict[str, Any] | None = None) -> Any:
    """Forward a request to the LiteLLM proxy and return the JSON response."""
    if not settings.litellm_enabled:
        raise HTTPException(status_code=501, detail="LiteLLM proxy is disabled (LITELLM_ENABLED=false).")

    url = f"{settings.litellm_base_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=settings.resilience.llm_timeout_seconds) as client:
            response = await client.request(method, url, headers=_headers(), json=json)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        log.warning("litellm_proxy_error", path=path, status=exc.response.status_code,
                    detail=exc.response.text[:300])
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"LiteLLM proxy error: {exc.response.text[:300]}",
        ) from exc
    except httpx.HTTPError as exc:
        log.warning("litellm_proxy_unreachable", path=path, error=str(exc)[:300])
        raise HTTPException(status_code=502, detail=f"LiteLLM proxy unreachable: {exc}") from exc


@router.get("/models", summary="List models available through the LiteLLM proxy")
async def list_models() -> dict[str, Any]:
    """Returns the model list from the LiteLLM proxy's /v1/models endpoint."""
    return await _proxy_request("GET", "/v1/models")


@router.get("/health", summary="LiteLLM proxy health")
async def proxy_health() -> dict[str, Any]:
    """Returns the health status of the LiteLLM proxy container."""
    return await _proxy_request("GET", "/health")


@router.post("/chat", summary="Test chat completion via the LiteLLM proxy")
async def proxy_chat(body: ProxyChatRequest) -> dict[str, Any]:
    """Send a test chat completion through the LiteLLM proxy.

    Useful for verifying that a specific model is reachable and returning
    valid responses before using it in agent runs.
    """
    payload = {
        "model": body.model,
        "messages": body.messages,
        "temperature": body.temperature,
        "max_tokens": body.max_tokens,
    }
    return await _proxy_request("POST", "/v1/chat/completions", json=payload)


@router.get("/spend", summary="LiteLLM spend tracking")
async def proxy_spend() -> dict[str, Any]:
    """Returns spend data from the LiteLLM proxy (if spend tracking is enabled)."""
    return await _proxy_request("GET", "/spend/logs")
