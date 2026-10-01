import logging
from typing import Optional
from src.storage.factory import get_knowledge_store
from src.retrieval.hybrid_retriever import HybridRetriever
from src.storage.schema import RetrievalResponse

logger = logging.getLogger(__name__)

class KnowledgeRetrievalService:
    """
    High-level retrieval service.
    Designed specifically to be consumed by:
    1. FastAPI REST API (`/api/v1/kb/search`)
    2. Question 1 LiveKit Voice Agent (`search_health_policy_kb` tool call)
    """

    def __init__(self, force_local: bool = False):
        self.store = get_knowledge_store(force_local=force_local)
        self.retriever = HybridRetriever(self.store)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None
    ) -> RetrievalResponse:
        """Standard retrieval endpoint."""
        return self.retriever.retrieve(query=query, top_k=top_k, category=category)

    def get_voice_tool_context(self, query: str) -> str:
        """
        Format retrieved chunks specifically for consumption by Question 1 voice bot.
        Enforces grounded citations and anti-hallucination fallback.
        """
        response = self.retrieve(query=query, top_k=3)

        if not response.grounded_answer_available or not response.results:
            return (
                "STATUS: INFORMATION_UNAVAILABLE\n"
                "GUIDELINE: Do not invent an answer or guess policy rules. "
                "State politely to the customer that this specific information is not available "
                "in your verified policy records and offer to transfer or connect them with a licensed human specialist."
            )

        context_blocks = []
        for res in response.results:
            context_blocks.append(
                f"[RECORD: {res.record_id} | SOURCE: {res.source} | CATEGORY: {res.category}]\n"
                f"Title: {res.title}\n"
                f"Content: {res.content}\n"
            )

        return (
            "STATUS: GROUNDED_INFO_FOUND\n"
            "INSTRUCTION: Answer the customer's query using ONLY the verified facts below. "
            "Cite the policy source clearly.\n\n"
            + "\n---\n".join(context_blocks)
        )

# Global default retrieval service instance
retrieval_service = KnowledgeRetrievalService()
