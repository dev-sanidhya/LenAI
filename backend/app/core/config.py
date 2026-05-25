from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_env: str = "development"
    app_secret_key: str = "change-me"
    log_level: str = "INFO"
    api_key: str = "dev-api-key-change-in-production"

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "lenai"
    postgres_user: str = "lenai"
    postgres_password: str = "lenai"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ChromaDB
    chroma_host: str = "chromadb"
    chroma_port: int = 8001
    chroma_collection_documents: str = "lenai_documents"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # Ollama
    ollama_base_url: str = "http://ollama:11434"
    ollama_llm_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_max_concurrency: int = 2

    # RAG
    chunk_size: int = 512
    chunk_overlap: int = 50
    rag_top_k_retrieve: int = 20
    rag_top_k_rerank: int = 5

    # Memory
    session_window_turns: int = 4
    session_summarize_after: int = 8

    # Upload
    max_upload_size_mb: int = 50
    allowed_extensions: str = "pdf,csv,xlsx,xls"

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_extensions.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
