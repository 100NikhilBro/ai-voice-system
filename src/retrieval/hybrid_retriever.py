from typing import List, Optional, Dict
import logging
from src.config import settings
from src.storage.base import BaseKnowledgeStore
from src.storage.schema import SearchResult, RetrievalResponse
from src.retrieval.embeddings import embedding_generator

logger = logging.getLogger(__name__)

class HybridRetriever:
    """
    Production-ready hybrid retriever combining:
    1. Dense semantic vector similarity (HNSW / Cosine)
    2. Sparse lexical full-text search (PostgreSQL FTS / SQLite BM25)
    3. Reciprocal Rank Fusion (RRF) for robust multi-modal ranking
    4. Exact source citation extraction and unavailable information fallback.
    """

    def __init__(
        self,
        store: BaseKnowledgeStore,
        rrf_k: int = 60,
        similarity_threshold: Optional[float] = None
    ):
        self.store = store
        self.rrf_k = rrf_k or settings.RRF_K
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else settings.RETRIEVAL_SCORE_THRESHOLD
        )

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None
    ) -> RetrievalResponse:
        """Execute hybrid search with RRF ranking and grounded citation formatting."""
        # 1. Dense Vector Search
        query_embedding = embedding_generator.embed_text(query)
        vector_results = self.store.search_vector(query_embedding, top_k=top_k * 2, category=category)

        # 2. Sparse Lexical Search
        text_results = self.store.search_text(query, top_k=top_k * 2, category=category)

        # Track best cosine similarity score
        top_vector_score = vector_results[0].score if vector_results else 0.0
        has_lexical_match = len(text_results) > 0

        # Check grounding threshold: must have either strong semantic similarity or lexical keyword match
        is_grounded = (top_vector_score >= self.similarity_threshold) or has_lexical_match

        if not is_grounded:
            logger.info(
                f"Query '{query}' failed grounding check (top vector sim: {top_vector_score:.4f} < {self.similarity_threshold}, text matches: {len(text_results)})."
            )
            return RetrievalResponse(
                query=query,
                results=[],
                total_found=0,
                grounded_answer_available=False,
                fallback_message="Information unavailable in verified source documents.",
                top_citation=None
            )

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores: Dict[str, float] = {}
        record_map: Dict[str, SearchResult] = {}

        # Vector RRF Contribution
        for rank, res in enumerate(vector_results, start=1):
            rrf_scores[res.record_id] = rrf_scores.get(res.record_id, 0.0) + (1.0 / (self.rrf_k + rank))
            record_map[res.record_id] = res

        # Text RRF Contribution
        for rank, res in enumerate(text_results, start=1):
            rrf_scores[res.record_id] = rrf_scores.get(res.record_id, 0.0) + (1.0 / (self.rrf_k + rank))
            if res.record_id not in record_map:
                record_map[res.record_id] = res

        # 4. Sort and construct merged ranked list
        sorted_records = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        final_results: List[SearchResult] = []

        for new_rank, (rec_id, score) in enumerate(sorted_records[:top_k], start=1):
            base_rec = record_map[rec_id]
            final_results.append(SearchResult(
                record_id=base_rec.record_id,
                title=base_rec.title,
                content=base_rec.content,
                category=base_rec.category,
                source=base_rec.source,
                version=base_rec.version,
                has_pii=base_rec.has_pii,
                score=round(score, 4),
                rank=new_rank,
                retrieval_method="hybrid_rrf"
            ))

        top_citation = f"Source: {final_results[0].source} (ID: {final_results[0].record_id})" if final_results else None

        return RetrievalResponse(
            query=query,
            results=final_results,
            total_found=len(final_results),
            grounded_answer_available=True,
            fallback_message=None,
            top_citation=top_citation
        )
