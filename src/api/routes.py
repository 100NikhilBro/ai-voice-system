from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from src.retrieval.service import retrieval_service
from src.ingestion.pipeline import run_ingestion
from src.storage.schema import RetrievalResponse, KnowledgeRecord

router = APIRouter(prefix="/api/v1/kb", tags=["Knowledge Base"])

class SearchRequest(BaseModel):
    query: str = Field(..., examples=["What is the waiting period for pre-existing conditions?"])
    top_k: int = Field(default=5, ge=1, le=20)
    category: Optional[str] = Field(default=None, examples=["policy_underwriting"])

class VoiceContextRequest(BaseModel):
    query: str = Field(..., examples=["Can someone aged 62 with hypertension get covered?"])

@router.post("/search", response_model=RetrievalResponse)
async def search_knowledge_base(request: SearchRequest):
    """
    Execute hybrid search over the health insurance knowledge base.
    Returns ranked chunks with exact source citations and grounded availability status.
    """
    try:
        response = retrieval_service.retrieve(
            query=request.query,
            top_k=request.top_k,
            category=request.category
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/voice-context")
async def get_voice_agent_context(request: VoiceContextRequest):
    """
    Specialized retrieval endpoint consumed by Question 1 LiveKit Voice Agent.
    Returns grounded context with source citations or explicit unavailability instructions.
    """
    try:
        context_text = retrieval_service.get_voice_tool_context(request.query)
        return {"query": request.query, "context": context_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ingest")
async def trigger_ingestion():
    """Trigger the end-to-end ingestion pipeline on domains/health_insurance/raw_docs/."""
    try:
        stats = run_ingestion()
        return {"status": "success", "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/records/{record_id}", response_model=KnowledgeRecord)
async def get_record_by_id(record_id: str):
    """Fetch a single knowledge base record by its unique ID."""
    rec = retrieval_service.store.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    return rec
