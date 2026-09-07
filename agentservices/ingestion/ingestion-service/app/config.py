"""Configuration for Ingestion Service."""
from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VectorBackend(str, Enum):
    """Which vector store to use for indexing."""

    OPENSEARCH = "opensearch"
    MONGODB = "mongodb"
    PINECONE = "pinecone"


class Settings(BaseSettings):
    """Service settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Service
    service_name: str = "ingestion"
    log_level: str = "INFO"

    # Database
    postgres_dsn: str = "postgresql+asyncpg://agentmesh:agentmesh@postgres:5432/agentmesh"
    postgres_sync_dsn: str = "postgresql+psycopg://agentmesh:agentmesh@postgres:5432/agentmesh"

    # Redis / Celery
    redis_dsn: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/0"

    # Object Storage
    storage_backend: str = "minio"  # minio | s3
    storage_endpoint_url: str = "http://minio:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "agentmesh-uploads"
    storage_region: str = "us-east-1"

    # Vector Backend
    vector_backend: VectorBackend = VectorBackend.OPENSEARCH

    # OpenSearch
    opensearch_host: str = "opensearch"
    opensearch_port: int = 9200
    opensearch_user: str = "admin"
    opensearch_password: str = "Agentmesh#2026"
    opensearch_use_ssl: bool = False
    opensearch_documents_index: str = "agentmesh-documents"

    # MongoDB
    mongodb_uri: str = "mongodb://mongodb:27017"
    mongodb_database: str = "agentmesh"
    mongodb_documents_collection: str = "document_chunks"

    # Pinecone
    pinecone_api_key: str | None = None
    pinecone_environment: str | None = None
    pinecone_index_name: str = "agentmesh-documents"

    # Embeddings
    embedding_provider: str = "openai"  # openai | litellm
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 64
    openai_api_key: str | None = None

    # LiteLLM (alternative)
    litellm_enabled: bool = False
    litellm_base_url: str = "http://litellm:4000"
    litellm_master_key: str = "sk-agentmesh-local"

    # Chunking
    chunk_size: int = 1200
    chunk_overlap: int = 180

    # Observability
    phoenix_enabled: bool = False
    phoenix_host: str = "phoenix"
    phoenix_grpc_port: int = 4317
    otel_exporter_otlp_endpoint: str = "http://phoenix:4317"

    @property
    def opensearch_url(self) -> str:
        scheme = "https" if self.opensearch_use_ssl else "http"
        return f"{scheme}://{self.opensearch_host}:{self.opensearch_port}"


settings = Settings()
