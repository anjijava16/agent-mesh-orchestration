"""Configuration for MCP Documents Server."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    mcp_server_name: str = "documents"
    mcp_server_port: int = 8081
    mcp_server_host: str = "0.0.0.0"
    log_level: str = "INFO"

    # Database
    postgres_dsn: str = "postgresql+asyncpg://agentmesh:agentmesh@localhost:5432/agentmesh"

    # Vector Store
    opensearch_host: str = "opensearch"
    opensearch_port: int = 9200
    opensearch_user: str = "admin"
    opensearch_password: str = "Agentmesh#2026"
    opensearch_use_ssl: bool = False
    opensearch_documents_index: str = "agentmesh-documents"

    @property
    def opensearch_url(self) -> str:
        scheme = "https" if self.opensearch_use_ssl else "http"
        return f"{scheme}://{self.opensearch_host}:{self.opensearch_port}"


settings = Settings()
