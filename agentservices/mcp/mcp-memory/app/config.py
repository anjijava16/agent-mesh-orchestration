"""Configuration for MCP Memory Server."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    mcp_server_name: str = "memory"
    mcp_server_port: int = 8083
    mcp_server_host: str = "0.0.0.0"
    log_level: str = "INFO"

    # Database
    postgres_dsn: str = "postgresql+asyncpg://agentmesh:agentmesh@localhost:5432/agentmesh"

    # Vector Backend
    vector_backend: str = "opensearch"  # opensearch | mongodb

    # OpenSearch
    opensearch_host: str = "opensearch"
    opensearch_port: int = 9200
    opensearch_user: str = "admin"
    opensearch_password: str = "Agentmesh#2026"
    opensearch_use_ssl: bool = False
    opensearch_memory_index: str = "agentmesh-longterm-memory"

    # MongoDB
    mongodb_uri: str = "mongodb://mongodb:27017"
    mongodb_database: str = "agentmesh"
    mongodb_memory_collection: str = "longterm_memory"

    # Embeddings
    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"


settings = Settings()
