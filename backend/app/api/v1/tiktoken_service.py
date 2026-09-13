"""tiktoken utilities.

Token counting / encode / decode against tiktoken encodings. Useful for sizing
prompts and debugging context budgets. Authenticated endpoint for token operations.
"""
from __future__ import annotations

from typing import Any

import tiktoken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(
    prefix="/services/tiktoken",
    tags=["services: tiktoken"],
    dependencies=[Depends(current_user)],
)

_DEFAULT_ENCODING = "cl100k_base"


def _get_encoding(encoding: str | None, model: str | None):
    """Get tiktoken encoding by name or model."""
    try:
        if model:
            return tiktoken.encoding_for_model(model)
        return tiktoken.get_encoding(encoding or _DEFAULT_ENCODING)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Unknown encoding/model: {exc}") from exc


class TextRequest(BaseModel):
    """Request body for text-based operations."""
    text: str = Field(max_length=100_000, description="Text to process")
    encoding: str | None = Field(None, description="Encoding name (e.g., cl100k_base)")
    model: str | None = Field(None, description="Model name (e.g., gpt-4)")


class TokensRequest(BaseModel):
    """Request body for token-based operations."""
    tokens: list[int] = Field(min_length=1, max_length=100_000, description="Token IDs")
    encoding: str | None = Field(None, description="Encoding name")
    model: str | None = Field(None, description="Model name")


@router.get("/encodings", summary="List available encodings")
async def list_encodings() -> dict[str, Any]:
    """List all available tiktoken encodings."""
    return {
        "encodings": tiktoken.list_encoding_names(),
        "default": _DEFAULT_ENCODING,
        "common_models": {
            "gpt-4": "cl100k_base",
            "gpt-3.5-turbo": "cl100k_base",
            "text-embedding-ada-002": "cl100k_base",
            "text-davinci-003": "p50k_base",
            "code-davinci-002": "p50k_base",
        }
    }


@router.post("/count", summary="Count tokens in text")
async def count_tokens(body: TextRequest) -> dict[str, Any]:
    """Count the number of tokens in the given text."""
    enc = _get_encoding(body.encoding, body.model)
    tokens = enc.encode(body.text)
    
    log.info("token_count", encoding=enc.name, characters=len(body.text), tokens=len(tokens))
    
    return {
        "encoding": enc.name,
        "characters": len(body.text),
        "token_count": len(tokens),
        "tokens_per_char": round(len(tokens) / len(body.text), 3) if body.text else 0
    }


@router.post("/encode", summary="Encode text to token ids")
async def encode_text(body: TextRequest) -> dict[str, Any]:
    """Encode text into token IDs using the specified encoding."""
    enc = _get_encoding(body.encoding, body.model)
    tokens = enc.encode(body.text)
    
    log.info("encode_text", encoding=enc.name, token_count=len(tokens))
    
    return {
        "encoding": enc.name,
        "token_count": len(tokens),
        "tokens": tokens,
        "sample_tokens": tokens[:10] if len(tokens) > 10 else tokens  # First 10 for preview
    }


@router.post("/decode", summary="Decode token ids to text")
async def decode_tokens(body: TokensRequest) -> dict[str, Any]:
    """Decode token IDs back into text."""
    enc = _get_encoding(body.encoding, body.model)
    try:
        text = enc.decode(body.tokens)
    except Exception as exc:  # noqa: BLE001
        log.error("decode_failed", error=str(exc), token_count=len(body.tokens))
        raise HTTPException(status_code=400, detail=f"Decode failed: {exc}") from exc
    
    log.info("decode_tokens", encoding=enc.name, character_count=len(text))
    
    return {
        "encoding": enc.name,
        "text": text,
        "character_count": len(text)
    }


@router.post("/batch_count", summary="Count tokens for multiple texts")
async def batch_count_tokens(texts: list[str] = Field(max_length=100)) -> dict[str, Any]:
    """Count tokens for multiple texts at once."""
    enc = tiktoken.get_encoding(_DEFAULT_ENCODING)
    
    results = []
    total_tokens = 0
    total_chars = 0
    
    for idx, text in enumerate(texts):
        tokens = enc.encode(text)
        token_count = len(tokens)
        char_count = len(text)
        
        total_tokens += token_count
        total_chars += char_count
        
        results.append({
            "index": idx,
            "characters": char_count,
            "tokens": token_count
        })
    
    log.info("batch_count", count=len(texts), total_tokens=total_tokens)
    
    return {
        "encoding": enc.name,
        "results": results,
        "summary": {
            "total_texts": len(texts),
            "total_characters": total_chars,
            "total_tokens": total_tokens,
            "avg_tokens_per_text": round(total_tokens / len(texts), 2) if texts else 0
        }
    }
