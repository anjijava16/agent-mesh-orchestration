"""Model provider abstraction.

One place that knows how to build a LangChain chat model, a raw provider client
and an embedding client for OpenAI / Anthropic / Google. Every framework adapter
asks this module rather than importing vendor SDKs directly, which is what lets
config.py flip a provider without touching agent code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import MODEL_CATALOGUE, ModelProvider, settings
from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.core.resilience import EMBEDDING_BREAKER, LLM_BREAKERS, with_resilience

log = get_logger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    provider: ModelProvider
    model: str
    temperature: float = 0.2
    max_tokens: int = 4096

    @classmethod
    def from_config(cls) -> ModelSpec:
        a = settings.agent
        return cls(provider=a.provider, model=a.model, temperature=a.temperature, max_tokens=a.max_tokens)

    def validate(self) -> ModelSpec:
        known = {m["id"] for m in MODEL_CATALOGUE.get(self.provider, [])}
        if known and self.model not in known:
            # Not fatal - operators pin new model ids ahead of the catalogue -
            # but we say so loudly in the logs.
            log.warning("model_not_in_catalogue", provider=self.provider.value, model=self.model)
        if settings.api_key_for(self.provider) is None:
            raise ValidationError(
                f"No API key configured for provider '{self.provider.value}'",
                details={"provider": self.provider.value, "env": f"{self.provider.value.upper()}_API_KEY"},
            )
        return self

    @property
    def breaker_key(self) -> str:
        return self.provider.value

    def langchain_id(self) -> str:
        """`init_chat_model` style identifier, e.g. 'anthropic:claude-sonnet-4-6'."""
        prefix = {
            ModelProvider.OPENAI: "openai",
            ModelProvider.ANTHROPIC: "anthropic",
            ModelProvider.GOOGLE: "google_genai",
        }[self.provider]
        return f"{prefix}:{self.model}"


def build_chat_model(spec: ModelSpec | None = None, **overrides: Any) -> Any:
    """Return a LangChain BaseChatModel. Used by LangGraph and DeepAgents."""
    spec = (spec or ModelSpec.from_config()).validate()
    kwargs: dict[str, Any] = {
        "temperature": spec.temperature,
        "max_tokens": spec.max_tokens,
        "timeout": settings.resilience.llm_timeout_seconds,
        "max_retries": 0,  # our retry wrapper owns this
        **overrides,
    }

    if spec.provider is ModelProvider.OPENAI:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=spec.model, api_key=settings.openai_api_key, **kwargs)

    if spec.provider is ModelProvider.ANTHROPIC:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=spec.model, api_key=settings.anthropic_api_key, **kwargs)

    from langchain_google_genai import ChatGoogleGenerativeAI

    kwargs.pop("timeout", None)
    kwargs["max_output_tokens"] = kwargs.pop("max_tokens")
    return ChatGoogleGenerativeAI(model=spec.model, google_api_key=settings.google_api_key, **kwargs)


def resolve_adk_model(spec: ModelSpec | None = None) -> Any:
    """ADK takes a bare Gemini model string, or a LiteLLM wrapper for everyone else."""
    spec = (spec or ModelSpec.from_config()).validate()
    if spec.provider is ModelProvider.GOOGLE:
        return spec.model
    from google.adk.models.lite_llm import LiteLlm

    prefix = "openai" if spec.provider is ModelProvider.OPENAI else "anthropic"
    return LiteLlm(model=f"{prefix}/{spec.model}")


class EmbeddingClient:
    """Thin embedding facade with batching, retry and a breaker."""

    def __init__(self, provider: ModelProvider | None = None, model: str | None = None) -> None:
        self.provider = provider or settings.ingestion.embedding_provider
        self.model = model or settings.ingestion.embedding_model
        self._client: Any = None

    def _ensure(self) -> Any:
        if self._client is not None:
            return self._client
        if self.provider is ModelProvider.OPENAI:
            from langchain_openai import OpenAIEmbeddings

            self._client = OpenAIEmbeddings(model=self.model, api_key=settings.openai_api_key, max_retries=0)
        elif self.provider is ModelProvider.GOOGLE:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            self._client = GoogleGenerativeAIEmbeddings(model=self.model, google_api_key=settings.google_api_key)
        else:
            # Anthropic does not ship an embedding model; use Voyage or fall back
            # to the OpenAI embedder so a Claude chat model still gets retrieval.
            from langchain_openai import OpenAIEmbeddings

            log.info("embedding_provider_fallback", requested="anthropic", used="openai")
            self._client = OpenAIEmbeddings(
                model=settings.ingestion.embedding_model, api_key=settings.openai_api_key, max_retries=0
            )
        return self._client

    @with_resilience(breaker=EMBEDDING_BREAKER, timeout=60, label="embed.query")
    async def embed_query(self, text: str) -> list[float]:
        return await self._ensure().aembed_query(text)

    @with_resilience(breaker=EMBEDDING_BREAKER, timeout=180, label="embed.documents")
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._ensure().aembed_documents(texts)

    def embed_documents_sync(self, texts: list[str]) -> list[list[float]]:
        """Celery workers are sync; keep a blocking path for them."""
        return self._ensure().embed_documents(texts)


_embedder: EmbeddingClient | None = None


def get_embedder() -> EmbeddingClient:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingClient()
    return _embedder


def llm_breaker(spec: ModelSpec) -> Any:
    return LLM_BREAKERS[spec.breaker_key]


def catalogue() -> dict[str, Any]:
    return {
        "providers": [
            {
                "id": provider.value,
                "configured": settings.api_key_for(provider) is not None,
                "models": models,
            }
            for provider, models in MODEL_CATALOGUE.items()
        ]
    }
