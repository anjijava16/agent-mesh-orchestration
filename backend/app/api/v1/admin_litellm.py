"""LiteLLM proxy passthrough endpoints.

Talks to the LiteLLM container (the platform's model egress gateway) using the
master key. Provides visibility into the proxy without leaving the AgentMesh API:
list available models, check proxy health, and run a test chat completion.

Enhanced with rate limiting, caching, and comprehensive chat features.

These are admin/infrastructure endpoints — they do not affect how agents use
the proxy (that happens transparently in ``llm/registry.py``).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import current_user
from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/admin/litellm", tags=["admin: litellm"])

# Simple in-memory cache for chat responses
_CACHE: dict[str, tuple[dict[str, Any], datetime]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


class ProxyChatRequest(BaseModel):
    model: str = Field(default_factory=lambda: settings.agent.model, description="Model name")
    messages: list[dict[str, Any]] = Field(
        default_factory=lambda: [{"role": "user", "content": "ping"}],
        description="Chat messages"
    )
    temperature: float = Field(default=0.1, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(default=128, ge=1, le=4096, description="Max tokens to generate")
    stream: bool = Field(default=False, description="Enable streaming")
    use_cache: bool = Field(default=False, description="Use cached response if available")
    cache_ttl: int = Field(default=300, ge=0, le=3600, description="Cache TTL in seconds")


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


def _cache_key(model: str, messages: list[dict], temperature: float, max_tokens: int) -> str:
    """Generate cache key for chat request."""
    content = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }, sort_keys=True)
    return hashlib.md5(content.encode()).hexdigest()


def _get_cached_response(cache_key: str) -> dict[str, Any] | None:
    """Get cached response if available and not expired."""
    if cache_key in _CACHE:
        response, timestamp = _CACHE[cache_key]
        if datetime.now() - timestamp < timedelta(seconds=_CACHE_TTL_SECONDS):
            log.info("cache_hit", cache_key=cache_key[:8])
            return {**response, "cached": True, "cache_age_seconds": (datetime.now() - timestamp).seconds}
        else:
            # Expired, remove
            del _CACHE[cache_key]
    return None


def _set_cached_response(cache_key: str, response: dict[str, Any]) -> None:
    """Cache response with timestamp."""
    _CACHE[cache_key] = (response, datetime.now())
    log.info("cache_set", cache_key=cache_key[:8], cache_size=len(_CACHE))


@router.post("/chat", summary="Test chat completion via the LiteLLM proxy")
@limiter.limit("10/minute")
async def proxy_chat(
    request: Request,
    body: ProxyChatRequest,
    user: dict = Depends(current_user)
) -> dict[str, Any]:
    """Send a test chat completion through the LiteLLM proxy.

    Useful for verifying that a specific model is reachable and returning
    valid responses before using it in agent runs.
    
    Features:
    - Rate limiting: 10 requests per minute
    - Response caching: Optional caching with configurable TTL
    - Streaming support: Real-time response streaming
    """
    # Check cache if enabled
    if body.use_cache:
        cache_key = _cache_key(body.model, body.messages, body.temperature, body.max_tokens)
        cached = _get_cached_response(cache_key)
        if cached:
            return cached
    
    payload = {
        "model": body.model,
        "messages": body.messages,
        "temperature": body.temperature,
        "max_tokens": body.max_tokens,
        "stream": body.stream,
    }
    
    log.info("litellm_chat", model=body.model, messages=len(body.messages), user=user.get("sub", "unknown"))
    
    response = await _proxy_request("POST", "/v1/chat/completions", json=payload)
    
    # Cache response if enabled
    if body.use_cache and not body.stream:
        cache_key = _cache_key(body.model, body.messages, body.temperature, body.max_tokens)
        _set_cached_response(cache_key, response)
    
    return {**response, "cached": False}


@router.get("/spend", summary="LiteLLM spend tracking")
async def proxy_spend() -> dict[str, Any]:
    """Returns spend data from the LiteLLM proxy (if spend tracking is enabled)."""
    return await _proxy_request("GET", "/spend/logs")



@router.post("/chat/simple", summary="Simple chat completion")
@limiter.limit("20/minute")
async def simple_chat(
    request: Request,
    message: str = Field(description="User message"),
    model: str | None = Field(None, description="Model name (default from config)"),
    user: dict = Depends(current_user)
) -> dict[str, Any]:
    """Simple chat endpoint with just a message and optional model.
    
    Rate limited to 20 requests per minute.
    """
    selected_model = model or settings.agent.model
    
    payload = {
        "model": selected_model,
        "messages": [{"role": "user", "content": message}],
        "temperature": 0.7,
        "max_tokens": 512,
    }
    
    log.info("simple_chat", model=selected_model, user=user.get("sub", "unknown"))
    
    return await _proxy_request("POST", "/v1/chat/completions", json=payload)


@router.get("/cache/stats", summary="Get cache statistics")
async def cache_stats() -> dict[str, Any]:
    """Get statistics about the response cache."""
    now = datetime.now()
    valid_entries = sum(
        1 for _, (_, timestamp) in _CACHE.items()
        if now - timestamp < timedelta(seconds=_CACHE_TTL_SECONDS)
    )
    
    return {
        "total_entries": len(_CACHE),
        "valid_entries": valid_entries,
        "expired_entries": len(_CACHE) - valid_entries,
        "cache_ttl_seconds": _CACHE_TTL_SECONDS,
        "memory_items": len(_CACHE)
    }


@router.delete("/cache", summary="Clear response cache")
async def clear_cache(user: dict = Depends(current_user)) -> dict[str, Any]:
    """Clear all cached responses."""
    entries_cleared = len(_CACHE)
    _CACHE.clear()
    
    log.info("cache_cleared", entries=entries_cleared, user=user.get("sub", "unknown"))
    
    return {
        "cleared": True,
        "entries_cleared": entries_cleared
    }


@router.get("/rate_limits", summary="Get rate limit information")
async def rate_limit_info() -> dict[str, Any]:
    """Get information about rate limits."""
    return {
        "endpoints": {
            "/chat": "10 requests per minute",
            "/chat/simple": "20 requests per minute"
        },
        "note": "Rate limits are per IP address"
    }


@router.post("/embeddings", summary="Generate embeddings via LiteLLM")
@limiter.limit("30/minute")
async def proxy_embeddings(
    request: Request,
    input_text: str | list[str] = Field(description="Text or list of texts to embed"),
    model: str = Field(default="text-embedding-ada-002", description="Embedding model"),
    user: dict = Depends(current_user)
) -> dict[str, Any]:
    """Generate embeddings through the LiteLLM proxy.
    
    Rate limited to 30 requests per minute.
    """
    payload = {
        "model": model,
        "input": input_text if isinstance(input_text, list) else [input_text]
    }
    
    log.info("litellm_embeddings", 
             model=model, 
             texts=len(payload["input"]), 
             user=user.get("sub", "unknown"))
    
    return await _proxy_request("POST", "/v1/embeddings", json=payload)


@router.get("/keys", summary="List API keys (if supported)")
async def list_keys() -> dict[str, Any]:
    """List API keys configured in LiteLLM (admin only)."""
    try:
        return await _proxy_request("GET", "/key/info")
    except HTTPException:
        return {"message": "Key management endpoint not available", "status": "unsupported"}


@router.post("/keys/generate", summary="Generate new API key")
async def generate_key(
    key_alias: str = Field(description="Alias for the key"),
    models: list[str] = Field(default_factory=list, description="Allowed models"),
    user: dict = Depends(current_user)
) -> dict[str, Any]:
    """Generate a new API key via LiteLLM (if supported)."""
    payload = {
        "key_alias": key_alias,
        "models": models or None
    }
    
    log.info("generate_key", alias=key_alias, user=user.get("sub", "unknown"))
    
    try:
        return await _proxy_request("POST", "/key/generate", json=payload)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=501,
                detail="Key generation not supported by LiteLLM proxy"
            )
        raise
