import json
import logging
from typing import List, Optional
import psycopg
from pgvector.psycopg import register_vector
from src.storage.base import BaseKnowledgeStore
from src.storage.schema import KnowledgeRecord, SearchResult
from src.config import settings

logger = logging.getLogger(__name__)

class PostgresKnowledgeStore(BaseKnowledgeStore):
    """
    Production storage engine using PostgreSQL with pgvector and Full-Text Search.
    Features:
    - HNSW vector index for cosine similarity (`<=>`).
    - GIN index on `tsvector` for full-text search.
    - Preserves metadata schema: record_id, title, content, category, source, version, has_pii.
    """

    def __init__(self, db_url: str):
        self.db_url = db_url

    def _get_connection(self):
        conn = psycopg.connect(self.db_url)
        register_vector(conn)
        return conn

    def initialize_schema(self) -> None:
        """Create vector extension, table, and indexes if they do not exist."""
        dim = settings.EMBEDDING_DIM
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS health_kb_records (
                        record_id VARCHAR(64) PRIMARY KEY,
                        title VARCHAR(255) NOT NULL,
                        content TEXT NOT NULL,
                        category VARCHAR(64) NOT NULL,
                        source VARCHAR(255) NOT NULL,
                        version VARCHAR(16) NOT NULL DEFAULT '1.0',
                        has_pii BOOLEAN NOT NULL DEFAULT FALSE,
                        pii_types TEXT[] DEFAULT '{{}}',
                        embedding vector({dim}),
                        tsv_content tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || content)) STORED,
                        metadata JSONB DEFAULT '{{}}',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                # Verify if embedding column has the expected dimension
                cur.execute("""
                    SELECT atttypmod FROM pg_attribute
                    WHERE attrelid = 'health_kb_records'::regclass AND attname = 'embedding';
                """)
                row = cur.fetchone()
                if row and row[0] != dim:
                    logger.warning(
                        f"PostgreSQL embedding column dimension ({row[0]}) does not match current EMBEDDING_DIM ({dim}). "
                        "Adjusting embedding column and recreating HNSW vector index."
                    )
                    cur.execute("DROP INDEX IF EXISTS idx_kb_vector;")
                    cur.execute("ALTER TABLE health_kb_records DROP COLUMN IF EXISTS embedding;")
                    cur.execute(f"ALTER TABLE health_kb_records ADD COLUMN embedding vector({dim});")

                cur.execute("CREATE INDEX IF NOT EXISTS idx_kb_vector ON health_kb_records USING hnsw (embedding vector_cosine_ops);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_kb_tsv ON health_kb_records USING gin (tsv_content);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_kb_category ON health_kb_records (category);")
                conn.commit()
                logger.info(f"PostgreSQL + pgvector schema initialized (dim={dim}).")

    def insert_records(self, records: List[KnowledgeRecord]) -> int:
        """Upsert knowledge records into PostgreSQL."""
        if not records:
            return 0

        insert_sql = """
            INSERT INTO health_kb_records (
                record_id, title, content, category, source, version,
                has_pii, pii_types, embedding, metadata
            ) VALUES (
                %(record_id)s, %(title)s, %(content)s, %(category)s, %(source)s, %(version)s,
                %(has_pii)s, %(pii_types)s, %(embedding)s, %(metadata)s
            )
            ON CONFLICT (record_id) DO UPDATE SET
                title = EXCLUDED.title,
                content = EXCLUDED.content,
                category = EXCLUDED.category,
                source = EXCLUDED.source,
                version = EXCLUDED.version,
                has_pii = EXCLUDED.has_pii,
                pii_types = EXCLUDED.pii_types,
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata;
        """

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for rec in records:
                    cur.execute(insert_sql, {
                        "record_id": rec.record_id,
                        "title": rec.title,
                        "content": rec.content,
                        "category": rec.category,
                        "source": rec.source,
                        "version": rec.version,
                        "has_pii": rec.has_pii,
                        "pii_types": rec.pii_types,
                        "embedding": rec.embedding,
                        "metadata": json.dumps(rec.metadata)
                    })
                conn.commit()

        return len(records)

    def search_vector(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        category: Optional[str] = None
    ) -> List[SearchResult]:
        """Dense vector search using cosine distance."""
        where_clause = "WHERE category = %(category)s" if category else ""
        sql = f"""
            SELECT record_id, title, content, category, source, version, has_pii,
                   1 - (embedding <=> %(q)s::vector) AS sim_score
            FROM health_kb_records
            {where_clause}
            ORDER BY embedding <=> %(q)s::vector
            LIMIT %(top_k)s;
        """

        params = {"q": query_embedding, "top_k": top_k}
        if category:
            params["category"] = category

        results = []
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                for rank, row in enumerate(rows, start=1):
                    results.append(SearchResult(
                        record_id=row[0],
                        title=row[1],
                        content=row[2],
                        category=row[3],
                        source=row[4],
                        version=row[5],
                        has_pii=row[6],
                        score=float(row[7]),
                        rank=rank,
                        retrieval_method="vector"
                    ))
        return results

    def search_text(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None
    ) -> List[SearchResult]:
        """Sparse lexical search using PostgreSQL FTS."""
        cat_filter = "AND category = %(category)s" if category else ""
        sql = f"""
            SELECT record_id, title, content, category, source, version, has_pii,
                   ts_rank_cd(tsv_content, websearch_to_tsquery('english', %(query)s)) AS rank_score
            FROM health_kb_records
            WHERE tsv_content @@ websearch_to_tsquery('english', %(query)s) {cat_filter}
            ORDER BY rank_score DESC
            LIMIT %(top_k)s;
        """

        params = {"query": query, "top_k": top_k}
        if category:
            params["category"] = category

        results = []
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                for rank, row in enumerate(rows, start=1):
                    results.append(SearchResult(
                        record_id=row[0],
                        title=row[1],
                        content=row[2],
                        category=row[3],
                        source=row[4],
                        version=row[5],
                        has_pii=row[6],
                        score=float(row[7]),
                        rank=rank,
                        retrieval_method="text"
                    ))
        return results

    def get_record(self, record_id: str) -> Optional[KnowledgeRecord]:
        """Retrieve single record by primary key."""
        sql = """
            SELECT record_id, title, content, category, source, version,
                   has_pii, pii_types, metadata
            FROM health_kb_records
            WHERE record_id = %(id)s;
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"id": record_id})
                row = cur.fetchone()
                if not row:
                    return None
                return KnowledgeRecord(
                    record_id=row[0],
                    title=row[1],
                    content=row[2],
                    category=row[3],
                    source=row[4],
                    version=row[5],
                    has_pii=row[6],
                    pii_types=row[7] or [],
                    metadata=row[8] if isinstance(row[8], dict) else json.loads(row[8] or '{}')
                )

    def count_records(self) -> int:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM health_kb_records;")
                return cur.fetchone()[0]

    def clear(self) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE health_kb_records;")
                conn.commit()
