from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone

class KnowledgeRecord(BaseModel):
    """
    Schema conforming strictly to the PDF Assessment Page 2 Field Example:
    - record_id: kb_product_001
    - title: Branch Partnership Benefits
    - content: Operational, marketing, and technology support...
    - category / source: partnership_benefits / website section
    - version / PII: 1.0 / false
    """
    record_id: str = Field(..., description="Unique record identifier, e.g. kb_health_001")
    title: str = Field(..., description="Document or section title")
    content: str = Field(..., description="Cleaned, normalized, and PII-masked content body")
    category: str = Field(..., description="Product, policy, qualification, faq, objection")
    source: str = Field(..., description="Source document and section citation, e.g. brochure.html#section")
    version: str = Field(default="1.0", description="Document or rule version")
    has_pii: bool = Field(default=False, description="Flag indicating if source had PII")
    pii_types: List[str] = Field(default_factory=list, description="Detected PII categories")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata tags")
    embedding: Optional[List[float]] = Field(default=None, description="Dense vector embedding")
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))

class SearchResult(BaseModel):
    """Individual retrieved search chunk with citation and score."""
    record_id: str
    title: str
    content: str
    category: str
    source: str
    version: str
    has_pii: bool
    score: float
    rank: int
    retrieval_method: str = "hybrid_rrf" # vector, text, or hybrid_rrf

class RetrievalResponse(BaseModel):
    """Structured response returned to caller (and voice bot)."""
    query: str
    results: List[SearchResult]
    total_found: int
    grounded_answer_available: bool
    fallback_message: Optional[str] = None
    top_citation: Optional[str] = None

class Q2EvaluationResult(BaseModel):
    """Structured benchmark evaluation result conforming to PDF Page 2 instructions."""
    query_id: str
    category: str
    user_question: str
    retrieved_record_id: Optional[str]
    retrieved_title: Optional[str]
    source_reference: Optional[str]
    similarity_score: float
    relevance_explanation: str
    verdict: str # CORRECT, PARTIALLY_CORRECT, INCORRECT, SAFE_FALLBACK
