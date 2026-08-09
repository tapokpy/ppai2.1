from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    BOT_TOKEN: str = ""
    ADMIN_IDS: str = ""

    # Local LLM (Ollama)
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    # Cloud LLM (Anthropic Claude)
    ANTHROPIC_API_KEY: str = ""
    CLOUD_MODEL_NAME: str = "claude-3-5-sonnet-20241022"
    CLOUD_DAILY_LIMIT_PER_USER: int = 50

    # RAG
    RAG_SCORE_THRESHOLD: float = 0.65
    CHROMA_PERSIST_DIR: str = "./data/chroma_db"
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"

    # Database
    POSTGRES_DSN: str = "postgresql+asyncpg://ppai:ppai@localhost:5432/ppai"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Observability
    LANGFUSE_HOST: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""

    # Security
    SECRET_KEY: str = "change-me-in-production"

    @property
    def admin_ids(self) -> list[int]:
        return [int(x) for x in self.ADMIN_IDS.split(",") if x.strip()]


settings = Settings()
