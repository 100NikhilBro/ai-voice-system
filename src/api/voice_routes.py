"""
Q1 Voice Agent API Routes
==========================
Exposes:
  WS  /ws/voice               – Main voice agent WebSocket
  GET /api/v1/voice/sessions  – List active sessions
  GET /api/v1/voice/transcripts/{session_id} – Fetch saved transcript
  POST /api/v1/voice/tts      – Standalone TTS endpoint (returns base64 MP3)
  GET  /                      – Serve the web calling UI
"""

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field

from src.voice.websocket_handler import handle_voice_websocket, _sessions
from src.voice.tts import synthesize_to_bytes
from src.config import settings

logger = logging.getLogger(__name__)

voice_router = APIRouter()

# Path to the web calling UI
WEB_UI_PATH = Path(__file__).parent.parent.parent / "web" / "index.html"

CONVERSATIONS_DIR = settings.KB_STORE_DIR / "conversations"


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@voice_router.websocket("/ws/voice")
async def voice_websocket_endpoint(ws: WebSocket):
    """Main voice agent WebSocket. See websocket_handler.py for protocol docs."""
    await handle_voice_websocket(ws)


# ── REST helpers ──────────────────────────────────────────────────────────────

@voice_router.get("/api/v1/voice/sessions", tags=["Voice Agent"])
async def list_active_sessions():
    """List currently active voice agent sessions."""
    return {
        "active_sessions": len(_sessions),
        "session_ids": list(_sessions.keys()),
    }


@voice_router.get("/api/v1/voice/transcripts", tags=["Voice Agent"])
async def list_transcripts():
    """List all saved conversation transcripts."""
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(CONVERSATIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    summaries = []
    for f in files[:50]:  # limit to latest 50
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            summaries.append({
                "session_id": data.get("session_id"),
                "started_at": data.get("started_at"),
                "ended_at": data.get("ended_at"),
                "outcome": data.get("outcome"),
                "turns": len(data.get("turns", [])),
                "qualification": data.get("qualification_state", {}),
            })
        except Exception as e:
            summaries.append({"file": f.name, "error": str(e)})
    return {"transcripts": summaries}


@voice_router.get("/api/v1/voice/transcripts/{session_id}", tags=["Voice Agent"])
async def get_transcript(session_id: str):
    """Fetch the full transcript for a completed session."""
    path = CONVERSATIONS_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Transcript {session_id} not found")
    return json.loads(path.read_text(encoding="utf-8"))


class TTSRequest(BaseModel):
    text: str = Field(..., max_length=1000)
    language: str = Field(default="en", pattern="^(en|tl|id)$")
    voice_id: str | None = Field(default=None)


@voice_router.post("/api/v1/voice/tts", tags=["Voice Agent"])
async def text_to_speech(request: TTSRequest):
    """
    Standalone TTS endpoint. Returns base64-encoded MP3 audio.
    Useful for previewing agent utterances without a full WS session.
    """
    try:
        audio = await synthesize_to_bytes(request.text, request.language, request.voice_id)
        return {
            "audio_b64": base64.b64encode(audio).decode(),
            "mime": "audio/mpeg",
            "bytes": len(audio),
            "language": request.language,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Web UI ────────────────────────────────────────────────────────────────────

@voice_router.get("/", response_class=HTMLResponse, tags=["Web UI"])
async def serve_web_ui():
    """Serve the web calling interface."""
    if WEB_UI_PATH.exists():
        return HTMLResponse(content=WEB_UI_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Web UI not found. Run from the project root.</h1>", status_code=404)
