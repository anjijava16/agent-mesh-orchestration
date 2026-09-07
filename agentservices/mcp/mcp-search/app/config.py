"""Configuration for MCP Search Server."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    mcp_server_name: str = "search"
    mcp_server_port: int = 8082
    mcp_server_host: str = "0.0.0.0"
    log_level: str = "INFO"

    # Web Search
    search_provider: str = "auto"  # auto | tavily | duckduckgo
    tavily_api_key: str | None = None

    # Database (for corpus stats)
    postgres_dsn: str = "postgresql+asyncpg://agentmesh:agentmesh@localhost:5432/agentmesh"

    # Vector Store (for corpus overview)
    opensearch_host: str = "opensearch"
    opensearch_port: int = 9200
    opensearch_user: str = "admin"
    opensearch_password: str = "Agentmesh#2026"
    opensearch_use_ssl: bool = False
    opensearch_documents_index: str = "agentmesh-documents"


settings = Settings()
