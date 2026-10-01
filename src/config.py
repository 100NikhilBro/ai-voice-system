import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))

    # PostgreSQL + pgvector
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/health_insurance_kb"
    )
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "health_insurance_kb")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))

    # Embedding provider selection
    # "local"  → sentence-transformers/all-MiniLM-L6-v2, dim=384, offline, no key
    # "openai" → OpenAI text-embedding-3-small, dim=1536, requires OPENAI_API_KEY
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "local")
    LOCAL_EMBEDDING_MODEL: str = os.getenv("LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    # OpenAI (optional – only used when EMBEDDING_PROVIDER=openai)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    # Vector dimension – resolved at import time from provider choice.
    # local provider (all-MiniLM-L6-v2) → 384
    # openai text-embedding-3-small     → 1536
    # PostgreSQL schema and LocalHybridStore both read this value.
    _PROVIDER_DIM_MAP = {
        "local": 384,
        "openai": 1536,
    }
    EMBEDDING_DIM: int = _PROVIDER_DIM_MAP.get(
        os.getenv("EMBEDDING_PROVIDER", "local").lower(), 384
    )

    # Paths
    RAW_DOCS_DIR: Path = BASE_DIR / "domains" / "health_insurance" / "raw_docs"
    KB_STORE_DIR: Path = BASE_DIR / "domains" / "health_insurance" / "kb_store"
    SQLITE_FALLBACK_PATH: Path = (
        BASE_DIR / "domains" / "health_insurance" / "kb_store" / "health_kb_local.db"
    )

    # Retrieval Thresholds
    RETRIEVAL_SCORE_THRESHOLD: float = float(os.getenv("RETRIEVAL_SCORE_THRESHOLD", "0.40"))
    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
    RRF_K: int = int(os.getenv("RRF_K", "60"))


settings = Settings()
