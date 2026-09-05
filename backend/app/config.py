"""Central configuration.

Everything that changes between environments lives here. Nothing else in the
codebase reads os.environ directly - if you need a knob, add it to a Settings
class and it becomes documented, typed and validated for free.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentFramework(str, Enum):
    """The four interchangeable multi-agent runtimes."""

    GOOGLE_ADK = "google_adk"
    LANGGRAPH = "langgraph"
    DEEPAGENTS = "deepagents"
    CLAUDE_AGENT_SDK = "claude_agent_sdk"


class ModelProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


# Model catalogue. The UI reads this over /api/v1/settings/models so operators
# can add a model here and have it appear in the picker without a frontend build.
MODEL_CATALOGUE: dict[ModelProvider, list[dict[str, Any]]] = {
    ModelProvider.ANTHROPIC: [
        {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6", "context": 200_000, "supports_tools": True},
        {"id": "claude-opus-4-1", "label": "Claude Opus 4.1", "context": 200_000, "supports_tools": True},
        {"id": "claude-haiku-4-5", "label": "Claude Haiku 4.5", "context": 200_000, "supports_tools": True},
    ],
    ModelProvider.OPENAI: [
        {"id": "gpt-4.1", "label": "GPT-4.1", "context": 1_000_000, "supports_tools": True},
        {"id": "gpt-4.1-mini", "label": "GPT-4.1 mini", "context": 1_000_000, "supports_tools": True},
        {"id": "o4-mini", "label": "o4-mini (reasoning)", "context": 200_000, "supports_tools": True},
    ],
    ModelProvider.GOOGLE: [
        {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "context": 1_000_000, "supports_tools": True},
        {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "context": 1_000_000, "supports_tools": True},
    ],
}


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", extra="ignore")

    host: str = "postgres"
    port: int = 5432
    user: str = "agentmesh"
    password: str = "agentmesh"
    db: str = "agentmesh"
    pool_size: int = 20
    max_overflow: int = 10
    pool_recycle_seconds: int = 1800
    echo: bool = False

    @property
    def async_dsn(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def sync_dsn(self) -> str:
        # Alembic and Celery workers use the sync driver.
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class OpenSearchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENSEARCH_", extra="ignore")

    host: str = "opensearch"
    port: int = 9200
    user: str = "admin"
    password: str = "Agentmesh#2026"
    use_ssl: bool = False
    verify_certs: bool = False
    timeout_seconds: int = 30

    documents_index: str = "agentmesh-documents"
    memory_index: str = "agentmesh-longterm-memory"
    embedding_dim: int = 1536

    # Hybrid search tuning
    bm25_top_k: int = 50
    knn_top_k: int = 50
    rrf_k: int = 60
    final_top_k: int = 8
    min_rerank_score: float = 0.0

    @property
    def url(self) -> str:
        scheme = "https" if self.use_ssl else "http"
        return f"{scheme}://{self.host}:{self.port}"


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    host: str = "redis"
    port: int = 6379
    db: int = 0
    celery_broker_db: int = 1
    celery_result_db: int = 2

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"

    @property
    def broker_url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.celery_broker_db}"

    @property
    def result_backend(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.celery_result_db}"


class StorageSettings(BaseSettings):
    """S3 on AWS, MinIO locally. Same API, different endpoint."""

    model_config = SettingsConfigDict(env_prefix="STORAGE_", extra="ignore")

    backend: Literal["minio", "s3"] = "minio"
    endpoint_url: str | None = "http://minio:9000"
    region: str = "us-east-1"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "agentmesh-uploads"
    presign_expiry_seconds: int = 3600
    max_upload_bytes: int = 200 * 1024 * 1024

    @model_validator(mode="after")
    def _clear_endpoint_for_aws(self) -> StorageSettings:
        if self.backend == "s3" and self.endpoint_url in ("", "http://minio:9000"):
            # Real S3 - let boto3 resolve the regional endpoint itself.
            self.endpoint_url = None
        return self


class ResilienceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RESILIENCE_", extra="ignore")

    # Retry
    max_attempts: int = 4
    initial_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 8.0
    backoff_multiplier: float = 2.0
    jitter_seconds: float = 0.3

    # Circuit breaker
    failure_threshold: int = 5
    success_threshold: int = 2
    breaker_reset_timeout_seconds: float = 30.0
    half_open_max_calls: int = 2

    # Timeouts
    llm_timeout_seconds: float = 120.0
    tool_timeout_seconds: float = 30.0
    search_timeout_seconds: float = 15.0


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_", extra="ignore")

    framework: AgentFramework = AgentFramework.LANGGRAPH
    provider: ModelProvider = ModelProvider.ANTHROPIC
    model: str = "claude-sonnet-4-6"
    temperature: float = 0.2
    max_tokens: int = 4096
    max_orchestrator_steps: int = 12
    parallel_fanout: bool = True
    enable_long_term_memory: bool = True
    short_term_window: int = 20  # messages replayed into the prompt
    long_term_top_k: int = 5

    @field_validator("temperature")
    @classmethod
    def _range(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("temperature must be between 0 and 2")
        return v


class IngestionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INGESTION_", extra="ignore")

    chunk_size: int = 1200
    chunk_overlap: int = 180
    embedding_provider: ModelProvider = ModelProvider.OPENAI
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 64
    max_pages_per_task: int = 50
    task_soft_time_limit: int = 900
    task_time_limit: int = 1200


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "AgentMesh"
    environment: Literal["local", "dev", "staging", "prod"] = "local"
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://localhost:8080"])
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    request_id_header: str = "X-Request-ID"

    # Credentials for the model providers.
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None

    # Optional tracing
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str | None = None

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    resilience: ResilienceSettings = Field(default_factory=ResilienceSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)

    def api_key_for(self, provider: ModelProvider) -> str | None:
        return {
            ModelProvider.OPENAI: self.openai_api_key,
            ModelProvider.ANTHROPIC: self.anthropic_api_key,
            ModelProvider.GOOGLE: self.google_api_key,
        }[provider]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
