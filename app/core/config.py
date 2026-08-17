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
    # Off by default per explicit request while docs/RAG setup is in
    # progress — the cascade stops at the local model instead of escalating.
    # Flip to True to re-enable cloud escalation.
    CLOUD_ENABLED: bool = False
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

    # RAG visualization admin panel (/dashboard bot command)
    # API_INTERNAL_BASE_URL: how the bot reaches the api service over the
    # docker network to mint a login link (server-to-server, X-Internal-Token
    # auth — see app/api/v1/endpoints/auth.py::generate_ott).
    # WEB_DASHBOARD_URL: the address the admin's own browser opens — must be
    # a real reachable host:port (not the docker-internal "api" hostname).
    API_INTERNAL_BASE_URL: str = "http://api:8000/api/v1"
    WEB_DASHBOARD_URL: str = "http://localhost:8080"

    # Showroom (Resolume Arena control + media library)
    # MEDIA_STORAGE_PATH is a path *inside the bot container* — in production
    # it's bind-mounted from the real Windows folder (D:/Pappai_Media) via
    # docker-compose.prod.yml, so the spec'd host path never needs to appear
    # in application code.
    MEDIA_STORAGE_PATH: str = "./data/media"
    MEDIA_STORAGE_QUOTA_GB: float = 100.0
    SCREENS_MAP_PATH: str = "./screens_map.yaml"
    # Resolume runs on the same machine as Docker Desktop (per spec) — from
    # inside a container that's the host, not localhost. host.docker.internal
    # is Docker Desktop's standard name for "the machine running Docker".
    RESOLUME_OSC_HOST: str = "host.docker.internal"
    RESOLUME_OSC_PORT: int = 7000
    RESOLUME_REST_BASE_URL: str = "http://host.docker.internal:8080/api/v1"

    # CAD-Engine (drawing analysis/generation) — outputs live in a
    # subfolder of the same media library (D:/Pappai_Media/Draw on the
    # host, MEDIA_STORAGE_PATH/Draw in-container).
    CAD_STORAGE_PATH: str = "./data/media/Draw"
    # Path to the ODA File Converter executable, IF installed — the
    # standard free (non-Python) tool for .dwg -> .dxf conversion, since
    # ezdxf itself only reads .dxf natively. Empty = .dwg uploads get a
    # clear "install the converter" message instead of silently failing.
    ODA_FILE_CONVERTER_PATH: str = ""
    CAPABILITIES_PATH: str = "./capabilities.yaml"

    # Warehouse (Warehouse -> Rack -> Shelf -> Cell stock, per
    # LOKI_WAREHOUSE_ECOSYSTEM_SPEC_v6.md). Google Sheets import reads a
    # PUBLIC sheet ("anyone with link can view") via API key — not a
    # service account — so no credentials file/JSON key ever needs to be
    # stored on disk. Empty = /import_sheet is disabled with a clear message.
    GOOGLE_SHEETS_API_KEY: str = ""
    # Non-CAD config/preset files attached to a Project via the
    # "проект3 <ID>" upload caption (app/bot/handlers/documents.py).
    PROJECT_FILES_PATH: str = "./data/project_files"

    # Tool calling (Локи calls Python functions instead of just answering in
    # text — e.g. "скачай это видео <url>" -> download_youtube). Off by
    # default until deployed and verified, same pattern as CLOUD_ENABLED.
    # TOOLS_USE_NATIVE_OLLAMA: live-tested in production against this exact
    # model/server/system-prompt combination (ollama==0.4.1 client,
    # qwen2.5:7b, Ollama server 0.32.9) — 8/8 test prompts across both tool
    # and non-tool cases picked correctly and consistently, so native
    # tools= is the default. False falls back to the prompt+JSON pattern
    # already used by the four *_parser.py modules.
    TOOLS_ENABLED: bool = False
    TOOLS_USE_NATIVE_OLLAMA: bool = True
    # Empty = generate_image tool disabled/hidden, same pattern as
    # ANTHROPIC_API_KEY. Provider not chosen yet (OpenAI/Stability/other).
    IMAGE_GEN_API_KEY: str = ""
    IMAGE_GEN_PROVIDER: str = ""
    # Per-tool kill switch, comma-separated tool names (e.g.
    # "warehouse_lookup,list_projects") — for rolling out new tools one at a
    # time with a live check in between, per explicit user request, rather
    # than exposing all of them to the model at once. A disabled tool is
    # simply never registered (app/core/dependencies.py::build_tool_registry)
    # — invisible to the model, not just blocked at dispatch time.
    TOOLS_DISABLED: str = ""

    @property
    def admin_ids(self) -> list[int]:
        return [int(x) for x in self.ADMIN_IDS.split(",") if x.strip()]

    @property
    def disabled_tools(self) -> set[str]:
        return {x.strip() for x in self.TOOLS_DISABLED.split(",") if x.strip()}


settings = Settings()
