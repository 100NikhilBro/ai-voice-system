"""
Q4 Live Insights — In-Process Call Session
===========================================
Manages an active call's insight pipeline state.
Used by both the WebSocket endpoint and the replay engine.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

from .signal_detector import SignalDetector
from .nudge_engine import NudgeEngine, Nudge
from .latency_tracker import LatencyTracker, LatencyRecord

logger = logging.getLogger(__name__)


class InsightSession:
    """
    A single live-call insight session.
    Maintains signal detector, nudge engine, latency tracker,
    and a queue of subscribers (WebSocket send callbacks).
    """

    def __init__(
        self,
        session_id: str,
        confidence_threshold: float = 0.65,
        cooldown_seconds: float = 30.0,
        expiry_seconds: float = 60.0,
        max_repetitions: int = 3,
    ):
        self.session_id = session_id
        self.created_at = time.time()

        self.signal_detector = SignalDetector(confidence_threshold=confidence_threshold)
        self.nudge_engine = NudgeEngine(
            confidence_threshold=confidence_threshold,
            cooldown_seconds=cooldown_seconds,
            expiry_seconds=expiry_seconds,
            max_repetitions=max_repetitions,
        )
        self.latency_tracker = LatencyTracker()

        # Async send callbacks for connected dashboard subscribers
        self._subscribers: list[Callable[[dict], Coroutine[Any, Any, None]]] = []
        self._turn_index = 0

    def subscribe(self, send_fn: Callable[[dict], Coroutine[Any, Any, None]]) -> None:
        self._subscribers.append(send_fn)

    def unsubscribe(self, send_fn: Callable[[dict], Coroutine[Any, Any, None]]) -> None:
        self._subscribers = [s for s in self._subscribers if s is not send_fn]

    async def process_utterance(
        self,
        text: str,
        speaker: str,
        t0_override_ms: Optional[float] = None,
        t1_override_ms: Optional[float] = None,
    ) -> List[Nudge]:
        """
        Process one utterance through the full pipeline with T0–T4 instrumentation.
        Broadcasts any new nudges to all subscribers.
        Returns list of new nudges generated.
        """
        self._turn_index += 1
        idx = self._turn_index

        # T0
        rec = self.latency_tracker.new_record(idx, speaker, text)
        if t0_override_ms:
            rec.t0_audio_received_ms = t0_override_ms

        # T1 (for live WS mode, transcription already done by client; minimal overhead)
        rec.t1_transcription_ms = t1_override_ms or (time.time() * 1000)

        # T2
        signals = self.signal_detector.detect(
            utterance=text,
            speaker=speaker,
            utterance_index=idx,
        )
        rec.t2_signal_detected_ms = time.time() * 1000

        # T3
        new_nudges = self.nudge_engine.process_signals(signals)
        rec.t3_nudge_generated_ms = time.time() * 1000
        rec.nudge_count = len(new_nudges)

        # T4 – broadcast to subscribers
        for nudge in new_nudges:
            msg = {
                "type":            "nudge",
                "session_id":      self.session_id,
                "nudge":           nudge.to_dict(),
                "latency_so_far":  round(time.time() * 1000 - rec.t0_audio_received_ms, 2),
            }
            await self._broadcast(msg)

        rec.t4_nudge_delivered_ms = time.time() * 1000
        self.latency_tracker.finalize_record(rec)

        return new_nudges

    async def _broadcast(self, msg: dict) -> None:
        """Send message to all subscribers, ignoring failures."""
        dead = []
        for send_fn in self._subscribers:
            try:
                await send_fn(msg)
            except Exception as e:
                logger.warning(f"[Insight] Subscriber delivery failed: {e}")
                dead.append(send_fn)
        for fn in dead:
            self._subscribers.remove(fn)

    def get_summary(self) -> dict:
        return {
            "session_id":    self.session_id,
            "turn_index":    self._turn_index,
            "nudge_stats":   self.nudge_engine.get_stats(),
            "latency_stats": self.latency_tracker.compute_stats(),
            "active_nudges": [n.to_dict() for n in self.nudge_engine.get_active_nudges()],
        }


# Global registry: session_id → InsightSession
_insight_sessions: Dict[str, InsightSession] = {}


def get_or_create_session(
    session_id: str,
    confidence_threshold: float = 0.65,
    cooldown_seconds: float = 30.0,
    expiry_seconds: float = 60.0,
    max_repetitions: int = 3,
) -> InsightSession:
    if session_id not in _insight_sessions:
        _insight_sessions[session_id] = InsightSession(
            session_id=session_id,
            confidence_threshold=confidence_threshold,
            cooldown_seconds=cooldown_seconds,
            expiry_seconds=expiry_seconds,
            max_repetitions=max_repetitions,
        )
    return _insight_sessions[session_id]


def close_session(session_id: str) -> Optional[dict]:
    sess = _insight_sessions.pop(session_id, None)
    return sess.get_summary() if sess else None


def list_sessions() -> List[str]:
    return list(_insight_sessions.keys())
