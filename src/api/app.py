from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from src.api.routes import router as kb_router
from src.api.voice_routes import voice_router
from src.retrieval.service import retrieval_service

app = FastAPI(
    title="HealthShield AI — Knowledge-Grounded Voice Agent",
    description=(
        "Q1: Real-time voice agent with grounded KB retrieval, "
        "lead qualification, and conversation logging. "
        "Q2: Production-ready hybrid knowledge base API."
    ),
    version="1.0.0"
)

# Enable CORS for web calling UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Q2 Knowledge Base routes
app.include_router(kb_router)

# Q1 Voice Agent routes (WebSocket + REST + Web UI)
app.include_router(voice_router)

# Serve static web assets (JS, CSS) from web/ directory
_web_dir = Path(__file__).parent.parent.parent / "web"
if _web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_web_dir)), name="static")


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check reporting storage engine and indexed record count."""
    store_type = type(retrieval_service.store).__name__
    record_count = retrieval_service.store.count_records()
    return {
        "status": "healthy",
        "service": "healthshield-ai-voice-agent",
        "storage_engine": store_type,
        "indexed_records": record_count,
        "components": {
            "q1_voice_agent": "active",
            "q2_knowledge_base": "active",
        }
    }
