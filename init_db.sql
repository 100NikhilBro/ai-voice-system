-- =========================================================
-- Health Insurance Knowledge Base Schema (Question 2)
-- PostgreSQL with pgvector & Full-Text Search
-- =========================================================

CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS health_kb_records;

CREATE TABLE health_kb_records (
    record_id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(64) NOT NULL,
    source VARCHAR(255) NOT NULL,
    version VARCHAR(16) NOT NULL DEFAULT '1.0',
    has_pii BOOLEAN NOT NULL DEFAULT FALSE,
    pii_types TEXT[] DEFAULT '{}',
    embedding vector(384),
    tsv_content tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || content)) STORED,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- HNSW Vector Index for Sub-second Cosine Similarity Search
CREATE INDEX IF NOT EXISTS idx_kb_vector ON health_kb_records USING hnsw (embedding vector_cosine_ops);

-- GIN Inverted Index for Sparse Lexical Full-Text Search
CREATE INDEX IF NOT EXISTS idx_kb_tsv ON health_kb_records USING gin (tsv_content);

-- B-Tree Index for Category and Source Filtering
CREATE INDEX IF NOT EXISTS idx_kb_category ON health_kb_records (category);
CREATE INDEX IF NOT EXISTS idx_kb_source ON health_kb_records (source);
