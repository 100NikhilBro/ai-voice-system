import sqlite3
import json
import logging
from typing import List, Optional
import numpy as np
from src.storage.base import BaseKnowledgeStore
from src.storage.schema import KnowledgeRecord, SearchResult

logger = logging.getLogger(__name__)

class LocalHybridKnowledgeStore(BaseKnowledgeStore):
    """
    Self-contained local hybrid store utilizing SQLite FTS5 (BM25)
    and in-memory NumPy cosine similarity for vector search.
    Implements the exact same schema, queries, and interface as PostgresKnowledgeStore.
    """

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self.initialize_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize_schema(self) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            # Standard relational table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS health_kb_records (
                    record_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source TEXT NOT NULL,
                    version TEXT NOT NULL DEFAULT '1.0',
                    has_pii INTEGER NOT NULL DEFAULT 0,
                    pii_types TEXT NOT NULL DEFAULT '[]',
                    embedding TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # FTS5 Virtual Table for BM25 Sparse Search
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS health_kb_fts USING fts5(
                    record_id UNINDEXED,
                    title,
                    content,
                    category,
                    tokenize = 'porter unicode61'
                );
            """)
            conn.commit()

    def insert_records(self, records: List[KnowledgeRecord]) -> int:
        if not records:
            return 0

        with self._get_connection() as conn:
            cur = conn.cursor()
            for rec in records:
                emb_json = json.dumps(rec.embedding) if rec.embedding else None
                cur.execute("""
                    INSERT OR REPLACE INTO health_kb_records (
                        record_id, title, content, category, source, version,
                        has_pii, pii_types, embedding, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    rec.record_id,
                    rec.title,
                    rec.content,
                    rec.category,
                    rec.source,
                    rec.version,
                    1 if rec.has_pii else 0,
                    json.dumps(rec.pii_types),
                    emb_json,
                    json.dumps(rec.metadata)
                ))

                # Update FTS index
                cur.execute("DELETE FROM health_kb_fts WHERE record_id = ?;", (rec.record_id,))
                cur.execute("""
                    INSERT INTO health_kb_fts (record_id, title, content, category)
                    VALUES (?, ?, ?, ?);
                """, (rec.record_id, rec.title, rec.content, rec.category))

            conn.commit()
        return len(records)

    def search_vector(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        category: Optional[str] = None
    ) -> List[SearchResult]:
        """Dense semantic search using NumPy cosine distance."""
        q_vec = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm

        with self._get_connection() as conn:
            cur = conn.cursor()
            if category:
                cur.execute("SELECT record_id, title, content, category, source, version, has_pii, embedding FROM health_kb_records WHERE category = ? AND embedding IS NOT NULL;", (category,))
            else:
                cur.execute("SELECT record_id, title, content, category, source, version, has_pii, embedding FROM health_kb_records WHERE embedding IS NOT NULL;")

            rows = cur.fetchall()

        if not rows:
            return []

        scored_records = []
        for row in rows:
            emb_str = row["embedding"]
            if not emb_str:
                continue
            doc_vec = np.array(json.loads(emb_str), dtype=np.float32)
            doc_norm = np.linalg.norm(doc_vec)
            if doc_norm > 0:
                doc_vec = doc_vec / doc_norm
            similarity = float(np.dot(q_vec, doc_vec))

            scored_records.append((similarity, row))

        # Sort descending by similarity
        scored_records.sort(key=lambda x: x[0], reverse=True)
        top_slice = scored_records[:top_k]

        results = []
        for rank, (score, row) in enumerate(top_slice, start=1):
            results.append(SearchResult(
                record_id=row["record_id"],
                title=row["title"],
                content=row["content"],
                category=row["category"],
                source=row["source"],
                version=row["version"],
                has_pii=bool(row["has_pii"]),
                score=score,
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
        """Sparse lexical BM25 search using SQLite FTS5."""
        # Sanitize query for FTS5 (remove punctuation that breaks FTS syntax)
        sanitized = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in query).strip()
        tokens = [t for t in sanitized.split() if len(t) > 2]
        if not tokens:
            return []

        fts_query = " OR ".join(tokens)

        with self._get_connection() as conn:
            cur = conn.cursor()
            try:
                if category:
                    sql = """
                        SELECT f.record_id, f.title, f.content, f.category,
                               r.source, r.version, r.has_pii,
                               bm25(health_kb_fts) AS bm25_rank
                        FROM health_kb_fts f
                        JOIN health_kb_records r ON f.record_id = r.record_id
                        WHERE health_kb_fts MATCH ? AND f.category = ?
                        ORDER BY bm25_rank ASC
                        LIMIT ?;
                    """
                    cur.execute(sql, (fts_query, category, top_k))
                else:
                    sql = """
                        SELECT f.record_id, f.title, f.content, f.category,
                               r.source, r.version, r.has_pii,
                               bm25(health_kb_fts) AS bm25_rank
                        FROM health_kb_fts f
                        JOIN health_kb_records r ON f.record_id = r.record_id
                        WHERE health_kb_fts MATCH ?
                        ORDER BY bm25_rank ASC
                        LIMIT ?;
                    """
                    cur.execute(sql, (fts_query, top_k))

                rows = cur.fetchall()
            except sqlite3.OperationalError as e:
                logger.warning(f"FTS query error: {e}")
                return []

        results = []
        for rank, row in enumerate(rows, start=1):
            # In SQLite FTS5, lower bm25 score is better (it's negative or small positive)
            raw_bm25 = row["bm25_rank"]
            norm_score = max(0.0, 1.0 / (1.0 + abs(raw_bm25)))

            results.append(SearchResult(
                record_id=row["record_id"],
                title=row["title"],
                content=row["content"],
                category=row["category"],
                source=row["source"],
                version=row["version"],
                has_pii=bool(row["has_pii"]),
                score=norm_score,
                rank=rank,
                retrieval_method="text"
            ))
        return results

    def get_record(self, record_id: str) -> Optional[KnowledgeRecord]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM health_kb_records WHERE record_id = ?;", (record_id,))
            row = cur.fetchone()
            if not row:
                return None
            return KnowledgeRecord(
                record_id=row["record_id"],
                title=row["title"],
                content=row["content"],
                category=row["category"],
                source=row["source"],
                version=row["version"],
                has_pii=bool(row["has_pii"]),
                pii_types=json.loads(row["pii_types"]),
                metadata=json.loads(row["metadata"]),
                embedding=json.loads(row["embedding"]) if row["embedding"] else None
            )

    def count_records(self) -> int:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM health_kb_records;")
            return cur.fetchone()[0]

    def clear(self) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM health_kb_records;")
            cur.execute("DELETE FROM health_kb_fts;")
            conn.commit()
