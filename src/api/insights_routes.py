"""
Q4 Live Insights API Routes
============================

Endpoints:
  WS  /ws/insights/{session_id}         — Live nudge stream (operator dashboard)
  POST /api/v1/insights/utterance        — Push one utterance for analysis
  POST /api/v1/insights/sessions         — Create a new insight session
  GET  /api/v1/insights/sessions         — List active sessions
  GET  /api/v1/insights/sessions/{sid}   — Get session summary + nudges
  DELETE /api/v1/insights/sessions/{sid} — Close session + return final report
  POST /api/v1/insights/replay           — Replay a saved transcript (real-time speed)
  GET  /api/v1/insights/nudges/{sid}     — Poll active nudges for a session (REST fallback)

WebSocket protocol (JSON):
  Client → Server:
    { "type": "utterance", "speaker": "customer|agent", "text": "...", "t0_ms": 1234567890.0 }
    { "type": "ping" }
    { "type": "close" }

  Server → Client:
    { "type": "nudge",    "session_id": "...", "nudge": {...}, "latency_so_far": 42.1 }
    { "type": "pong" }
    { "type": "ack",      "turn_index": 3, "signals_detected": 1, "nudges_generated": 1 }
    { "type": "summary",  ...session summary... }
    { "type": "error",    "message": "..." }
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.insights.session import (
    get_or_create_session,
    close_session,
    list_sessions,
    _insight_sessions,
)
from src.insights.replay_engine import TranscriptReplayEngine

logger = logging.getLogger(__name__)
insights_router = APIRouter(prefix="/api/v1/insights", tags=["Q4 Live Insights"])

# Path to saved recordings for replay
RECORDINGS_DIR = Path(__file__).parent.parent.parent / "artifacts" / "recordings"


# ── Pydantic models ───────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    session_id: str | None = Field(default=None, description="Optional custom session ID")
    confidence_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    cooldown_seconds: float = Field(default=30.0, ge=0.0)
    expiry_seconds: float = Field(default=60.0, ge=1.0)
    max_repetitions: int = Field(default=3, ge=1)


class UtteranceRequest(BaseModel):
    session_id: str
    speaker: str = Field(..., pattern="^(agent|customer)$")
    text: str = Field(..., min_length=1, max_length=2000)
    t0_ms: float | None = Field(default=None, description="T0 epoch ms override")


class ReplayRequest(BaseModel):
    transcript_name: str = Field(..., description="Recording folder name, e.g. call_01_cooperative")
    confidence_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    cooldown_seconds: float = Field(default=5.0, ge=0.0,
                                     description="Reduced for replay demonstration")
    expiry_seconds: float = Field(default=120.0, ge=1.0)
    max_repetitions: int = Field(default=5, ge=1)
    replay_speed: float = Field(default=3.0, ge=0.1, le=10.0,
                                 description="Multiplier: 3.0 = 3x real-time speed")


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@insights_router.websocket("/ws/{session_id}")
async def insights_websocket(ws: WebSocket, session_id: str):
    """
    Live nudge stream for an operator dashboard.
    Subscribe to get real-time nudge events as utterances are processed.
    """
    await ws.accept()
    logger.info(f"[Insights WS] Client connected to session {session_id}")

    session = get_or_create_session(session_id)

    async def send_to_client(msg: dict):
        await ws.send_json(msg)

    session.subscribe(send_to_client)

    # Send current active nudges immediately on connect
    await ws.send_json({
        "type": "connected",
        "session_id": session_id,
        "active_nudges": [n.to_dict() for n in session.nudge_engine.get_active_nudges()],
    })

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "utterance":
                speaker = msg.get("speaker", "customer")
                text = msg.get("text", "").strip()
                t0_ms = msg.get("t0_ms")
                if not text:
                    continue

                t1_ms = time.time() * 1000  # transcription done by client
                new_nudges = await session.process_utterance(
                    text=text,
                    speaker=speaker,
                    t0_override_ms=t0_ms,
                    t1_override_ms=t1_ms,
                )

                rec_list = session.latency_tracker.get_records()
                latest_rec = rec_list[-1] if rec_list else None
                await ws.send_json({
                    "type":              "ack",
                    "turn_index":        session._turn_index,
                    "signals_detected":  len(new_nudges),
                    "nudges_generated":  len(new_nudges),
                    "e2e_latency_ms":    round(latest_rec.end_to_end_latency_ms, 2) if latest_rec else 0,
                })

            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

            elif msg_type == "summary":
                await ws.send_json({"type": "summary", **session.get_summary()})

            elif msg_type == "close":
                summary = close_session(session_id)
                await ws.send_json({"type": "summary", **(summary or {})})
                break

    except WebSocketDisconnect:
        logger.info(f"[Insights WS] Client disconnected from {session_id}")
    except Exception as e:
        logger.error(f"[Insights WS] Error: {e}")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        session.unsubscribe(send_to_client)


# ── REST endpoints ────────────────────────────────────────────────────────────

@insights_router.post("/sessions", summary="Create insight session")
async def create_session(req: CreateSessionRequest):
    sid = req.session_id or str(uuid.uuid4())[:8]
    sess = get_or_create_session(
        session_id=sid,
        confidence_threshold=req.confidence_threshold,
        cooldown_seconds=req.cooldown_seconds,
        expiry_seconds=req.expiry_seconds,
        max_repetitions=req.max_repetitions,
    )
    return {"session_id": sid, "created": True, "config": req.model_dump()}


@insights_router.get("/sessions", summary="List active insight sessions")
async def list_active_sessions():
    return {"sessions": list_sessions(), "count": len(list_sessions())}


@insights_router.get("/sessions/{session_id}", summary="Get session summary")
async def get_session(session_id: str):
    if session_id not in _insight_sessions:
        raise HTTPException(404, f"Session {session_id!r} not found")
    return _insight_sessions[session_id].get_summary()


@insights_router.delete("/sessions/{session_id}", summary="Close session + final report")
async def close_insight_session(session_id: str):
    summary = close_session(session_id)
    if summary is None:
        raise HTTPException(404, f"Session {session_id!r} not found")
    return {"closed": True, "final_report": summary}


@insights_router.post("/utterance", summary="Push utterance for live analysis")
async def push_utterance(req: UtteranceRequest):
    """
    Push a single utterance to an active insight session.
    Suitable for REST polling clients that cannot use WebSocket.
    """
    if req.session_id not in _insight_sessions:
        raise HTTPException(404, f"Session {req.session_id!r} not found. Create it first.")
    session = _insight_sessions[req.session_id]
    t0_ms = req.t0_ms or (time.time() * 1000)
    t1_ms = time.time() * 1000
    new_nudges = await session.process_utterance(
        text=req.text,
        speaker=req.speaker,
        t0_override_ms=t0_ms,
        t1_override_ms=t1_ms,
    )
    rec_list = session.latency_tracker.get_records()
    latest_rec = rec_list[-1] if rec_list else None
    return {
        "nudges_generated": len(new_nudges),
        "nudges": [n.to_dict() for n in new_nudges],
        "e2e_latency_ms": round(latest_rec.end_to_end_latency_ms, 2) if latest_rec else 0,
        "active_nudges": [n.to_dict() for n in session.nudge_engine.get_active_nudges()],
    }


@insights_router.get("/nudges/{session_id}", summary="Poll active nudges (REST fallback)")
async def poll_nudges(session_id: str):
    """REST polling endpoint for clients that cannot use WebSocket."""
    if session_id not in _insight_sessions:
        raise HTTPException(404, f"Session {session_id!r} not found")
    session = _insight_sessions[session_id]
    return {
        "session_id":    session_id,
        "active_nudges": [n.to_dict() for n in session.nudge_engine.get_active_nudges()],
        "stats":         session.nudge_engine.get_stats(),
    }


@insights_router.post("/replay", summary="Replay a saved transcript at real-time speed")
async def replay_transcript(req: ReplayRequest):
    """
    Replay a saved call recording at real-time speed (default 3x for demo).
    Processes utterances one-by-one with inter-turn delays — NOT post-call analysis.
    Returns final nudge report with latency measurements.
    """
    # Find the transcript
    transcript_path = _find_transcript(req.transcript_name)
    if not transcript_path:
        available = [p.name for p in RECORDINGS_DIR.iterdir() if p.is_dir()]
        raise HTTPException(
            404,
            f"Transcript {req.transcript_name!r} not found. "
            f"Available: {available}"
        )

    engine = TranscriptReplayEngine(
        transcript_path=transcript_path,
        confidence_threshold=req.confidence_threshold,
        cooldown_seconds=req.cooldown_seconds,
        expiry_seconds=req.expiry_seconds,
        max_repetitions=req.max_repetitions,
        replay_speed=req.replay_speed,
    )

    nudge_log: list[dict] = []

    async def on_nudge(nudge, rec):
        nudge_log.append({
            "nudge": nudge.to_dict(),
            "e2e_latency_ms": round(rec.end_to_end_latency_ms, 2),
        })

    await engine.run(nudge_callback=on_nudge)
    summary = engine.get_summary()
    summary["nudge_log"] = nudge_log

    return summary


def _find_transcript(name: str) -> Optional[Path]:
    """Find transcript.json in a named recording folder."""
    candidate = RECORDINGS_DIR / name / "transcript.json"
    if candidate.exists():
        return candidate
    # Try result.json for Q3 format
    candidate2 = RECORDINGS_DIR / name / "result.json"
    if candidate2.exists():
        return candidate2
    return None
