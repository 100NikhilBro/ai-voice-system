import logging
import psycopg
from src.config import settings
from src.storage.base import BaseKnowledgeStore
from src.storage.postgres_store import PostgresKnowledgeStore
from src.storage.local_store import LocalHybridKnowledgeStore

logger = logging.getLogger(__name__)

def get_knowledge_store(force_local: bool = False) -> BaseKnowledgeStore:
    """
    Knowledge store factory.
    Attempts PostgreSQL + pgvector connection first.
    If PostgreSQL is unavailable or force_local=True, falls back to the embedded
    SQLite FTS5 + NumPy hybrid vector store.
    """
    if not force_local and settings.DATABASE_URL:
        try:
            # Quick probe connection with 2-second timeout
            with psycopg.connect(settings.DATABASE_URL, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
            logger.info("Connected to primary PostgreSQL database with pgvector.")
            pg_store = PostgresKnowledgeStore(settings.DATABASE_URL)
            pg_store.initialize_schema()
            return pg_store
        except Exception as e:
            logger.warning(
                f"PostgreSQL connection failed ({e}). "
                "Operating in self-contained local hybrid mode (SQLite FTS5 + NumPy Vector)."
            )

    # Fallback to local embedded store
    settings.SQLITE_FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    return LocalHybridKnowledgeStore(str(settings.SQLITE_FALLBACK_PATH))
