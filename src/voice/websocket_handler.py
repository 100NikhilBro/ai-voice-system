"""
WebSocket Voice Agent Handler
==============================
FastAPI WebSocket endpoint that drives the Q1 voice agent session.

Protocol (JSON over WebSocket):
---------------------------------
Client → Server:
  { "type": "transcript", "text": "<customer utterance>", "language": "en" }
  { "type": "start" }   ← initiate session, triggers opening greeting
  { "type": "end" }     ← close session

Server → Client:
  { "type": "agent_text",  "text": "...", "state": "...", "meta": {...} }
  { "type": "agent_audio", "data": "<base64 mp3>" }
  { "type": "session_started", "session_id": "...", "opening": "..." }
  { "type": "session_ended",   "session_id": "...", "transcript_path": "..." }
  { "type": "error", "message": "..." }

Audio flow:
  Browser Web Speech API → text → WS → agent → text → Edge-TTS → base64 mp3 → browser
"""

import asyncio
import base64
import json
import logging
import traceback
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect

from src.voice.agent import VoiceAgent
from src.voice.conversation_logger import ConversationLogger
from src.voice.tts import synthesize_to_bytes

logger = logging.getLogger(__name__)

# Active sessions: session_id → (agent, logger)
_sessions: Dict[str, tuple[VoiceAgent, ConversationLogger]] = {}


async def _send_json(ws: WebSocket, data: dict) -> None:
    """Helper to send JSON safely."""
    try:
        await ws.send_json(data)
    except Exception as e:
        logger.warning(f"[WS] send failed: {e}")


async def _synthesize_and_send(ws: WebSocket, text: str, language: str = "en") -> None:
    """Synthesize TTS and send as base64-encoded MP3 chunks."""
    try:
        audio_bytes = await synthesize_to_bytes(text, language=language)
        b64 = base64.b64encode(audio_bytes).decode("utf-8")
        await _send_json(ws, {"type": "agent_audio", "data": b64, "mime": "audio/mpeg"})
    except Exception as e:
        logger.error(f"[TTS] Synthesis error: {e}")
        await _send_json(ws, {"type": "error", "message": f"TTS error: {e}"})


async def handle_voice_websocket(ws: WebSocket) -> None:
    """
    Main WebSocket handler. Accepts one client connection and runs
    the full voice agent session lifecycle.
    """
    await ws.accept()
    logger.info("[WS] New WebSocket connection accepted")

    agent: VoiceAgent | None = None
    conv_logger: ConversationLogger | None = None
    language = "en"

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            # ── SESSION START ──────────────────────────────────────────────
            if msg_type == "start":
                language = msg.get("language", "en")
                conv_logger = ConversationLogger()
                agent = VoiceAgent(conv_logger.session_id)
                _sessions[conv_logger.session_id] = (agent, conv_logger)

                opening = agent.get_opening_message()
                conv_logger.log_turn("agent", opening)

                await _send_json(ws, {
                    "type": "session_started",
                    "session_id": conv_logger.session_id,
                    "opening": opening,
                })
                # Send TTS for the opening
                await _synthesize_and_send(ws, opening, language)

            # ── CUSTOMER TRANSCRIPT ────────────────────────────────────────
            elif msg_type == "transcript":
                if agent is None or conv_logger is None:
                    await _send_json(ws, {"type": "error", "message": "Session not started. Send {type:start} first."})
                    continue

                utterance = msg.get("text", "").strip()
                language = msg.get("language", language)
                if not utterance:
                    continue

                conv_logger.log_turn("customer", utterance)
                logger.info(f"[Agent/{agent.session_id}] Customer: {utterance!r}")

                # Process through agent state machine
                agent_text, meta = agent.process(utterance)
                conv_logger.log_turn("agent", agent_text, meta)
                conv_logger.update_qualification(meta.get("qualification_profile", {}))

                logger.info(f"[Agent/{agent.session_id}] Agent [{meta['state']}]: {agent_text!r}")

                # Send text response
                await _send_json(ws, {
                    "type": "agent_text",
                    "text": agent_text,
                    "state": meta["state"],
                    "meta": meta,
                })
                # Send TTS audio
                await _synthesize_and_send(ws, agent_text, language)

                # Auto-close if session ended
                if meta.get("ended"):
                    transcript_path = conv_logger.close("completed")
                    await _send_json(ws, {
                        "type": "session_ended",
                        "session_id": agent.session_id,
                        "transcript_path": str(transcript_path),
                    })
                    break

                if meta.get("escalated") and meta["state"] == "escalation":
                    # After escalation message sent, wait for one more turn then close
                    pass  # agent will handle the final turn and set state=ended

            # ── SESSION END ────────────────────────────────────────────────
            elif msg_type == "end":
                if conv_logger:
                    transcript_path = conv_logger.close("user_terminated")
                    await _send_json(ws, {
                        "type": "session_ended",
                        "session_id": agent.session_id if agent else "unknown",
                        "transcript_path": str(transcript_path),
                    })
                break

            else:
                await _send_json(ws, {"type": "error", "message": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected")
    except Exception as e:
        logger.error(f"[WS] Unhandled error: {e}\n{traceback.format_exc()}")
        try:
            await _send_json(ws, {"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        if conv_logger and conv_logger.outcome is None:
            conv_logger.close("disconnected")
        if agent and agent.session_id in _sessions:
            del _sessions[agent.session_id]
        logger.info("[WS] WebSocket session cleaned up")
