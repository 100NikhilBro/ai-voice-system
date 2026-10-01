import json
import logging
from pathlib import Path
from typing import List, Dict, Any
from src.config import settings
from src.ingestion.parser import parser
from src.ingestion.cleaner import cleaner
from src.ingestion.normalizer import normalizer
from src.pii.detector import pii_detector
from src.ingestion.chunker import chunker
from src.retrieval.embeddings import get_embedding_provider
from src.storage.factory import get_knowledge_store
from src.storage.schema import KnowledgeRecord

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IngestionPipeline:
    """
    End-to-end ingestion pipeline:
    ingest → parse/clean → deduplicate → normalize → PII handling → chunk → embed → store → export
    """

    def __init__(self, raw_docs_dir: Path = settings.RAW_DOCS_DIR, force_local: bool = False):
        self.raw_docs_dir = Path(raw_docs_dir)
        self.store = get_knowledge_store(force_local=force_local)
        self.embedder = get_embedding_provider()
        logger.info(
            f"IngestionPipeline ready. "
            f"Embedding provider: {type(self.embedder).__name__}, dim={self.embedder.dimension}"
        )

    def run(self) -> Dict[str, Any]:
        """Execute full ingestion pipeline across all raw documents."""
        if not self.raw_docs_dir.exists():
            raise FileNotFoundError(f"Raw documents directory not found: {self.raw_docs_dir}")

        doc_files = [f for f in self.raw_docs_dir.iterdir() if f.is_file() and not f.name.startswith('.')]
        logger.info(f"Starting ingestion pipeline on {len(doc_files)} files from {self.raw_docs_dir}")

        all_records: List[KnowledgeRecord] = []
        stats = {
            "files_processed": 0,
            "paragraphs_deduplicated": 0,
            "pii_records_detected": 0,
            "total_chunks_created": 0,
            "records_inserted": 0,
            "categories": {}
        }

        for file_path in doc_files:
            logger.info(f"Processing: {file_path.name}")

            # 1. Parse Document
            parsed = parser.parse_file(file_path)

            # 2. Clean Boilerplate & Formatting
            cleaned_text = cleaner.clean_text(parsed["raw_text"])

            # 3. Deduplicate Near-Duplicate Paragraphs
            dedup_text, dedup_count = cleaner.deduplicate_paragraphs(cleaned_text)
            stats["paragraphs_deduplicated"] += dedup_count

            # 4. PII Identification and Protection
            masked_text, pii_info = pii_detector.mask(dedup_text)
            has_pii = pii_info["has_pii"]
            pii_types = pii_info["pii_types"]
            if has_pii:
                stats["pii_records_detected"] += 1
                logger.info(f"PII identified and protected in {file_path.name}: {pii_types}")

            # 5. Normalize Terminology and Category
            explicit_cat = parsed.get("category", "")
            category = normalizer.normalize_category(file_path.name, explicit_cat)
            normalized_text = normalizer.normalize_terminology(masked_text)

            stats["categories"][category] = stats["categories"].get(category, 0) + 1

            # 6. Semantic Chunking into KnowledgeRecords
            chunks = chunker.chunk_document(
                doc_data=parsed,
                cleaned_text=normalized_text,
                category=category,
                source=file_path.name,
                has_pii=has_pii,
                pii_types=pii_types
            )
            stats["total_chunks_created"] += len(chunks)

            # 7. Generate Embeddings for each chunk (batch per document)
            texts = [f"{c.title}\n{c.content}" for c in chunks]
            embeddings = self.embedder.embed_batch(texts)
            for chunk, emb in zip(chunks, embeddings):
                chunk.embedding = emb
                all_records.append(chunk)

            stats["files_processed"] += 1

        # 8. Store into Knowledge Store (Postgres / Local Hybrid)
        inserted_count = self.store.insert_records(all_records)
        stats["records_inserted"] = inserted_count

        # 9. Export verifiable JSON dump to kb_store
        export_path = settings.KB_STORE_DIR / "health_kb_records.json"
        settings.KB_STORE_DIR.mkdir(parents=True, exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in all_records], f, indent=2, default=str)

        logger.info(f"Ingestion complete: {inserted_count} records indexed. Exported to {export_path}")
        return stats

def run_ingestion(force_local: bool = False):
    pipeline = IngestionPipeline(force_local=force_local)
    return pipeline.run()

if __name__ == "__main__":
    run_ingestion()
