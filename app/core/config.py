from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    BOT_TOKEN: str = ""
    ADMIN_IDS: str = ""

    # Local LLM (Ollama)
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    # Lower temperature/top_p than Ollama's defaults (0.8/0.9) to make the
    # local model less prone to confidently inventing specifics.
    OLLAMA_TEMPERATURE: float = 0.35
    OLLAMA_TOP_P: float = 0.85
    OLLAMA_TOP_K: int = 40
    OLLAMA_REPEAT_PENALTY: float = 1.15
    OLLAMA_NUM_PREDICT: int = 512

    # Speech-to-text (Faster-Whisper) for voice messages
    WHISPER_MODEL_SIZE: str = "small"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_LANGUAGE: str = "ru"

    # Cloud LLM (Anthropic Claude)
    ANTHROPIC_API_KEY: str = ""
    CLOUD_MODEL_NAME: str = "claude-3-5-sonnet-20241022"
    CLOUD_DAILY_LIMIT_PER_USER: int = 50
    # Optional HTTP proxy for Claude API calls only (e.g. http://gluetun:8888
    # in production, to route just this traffic through a VPN). Empty = direct.
    ANTHROPIC_PROXY_URL: str = ""

    # RAG
    # Raised from 0.65: at 0.65 even weak/tangential matches were being
    # treated as grounding context, which the local model would then answer
    # from confidently regardless of how loosely it actually applied.
    RAG_SCORE_THRESHOLD: float = 0.75
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
    INTERNAL_API_TOKEN: str = "change-me-internal-token"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_HOURS: int = 8
    OTT_EXPIRES_SECONDS: int = 300

    # GitHub Planning (Loki: in-chat "todo3"/"план3" capture -> PLANNING.md)
    GITHUB_TOKEN: str = ""
    GITHUB_REPO: str = "tapokpy/ppai"
    GITHUB_PLANNING_FILE_PATH: str = "PLANNING.md"
    GITHUB_PLANNING_BRANCH: str = "claude/review-files-plan-rn4l2a"

    @property
    def admin_ids(self) -> list[int]:
        return [int(x) for x in self.ADMIN_IDS.split(",") if x.strip()]


settings = Settings()
