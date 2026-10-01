"""
Transcript Replay Engine
=========================
Replays a saved call transcript at real-time speed (one utterance per
simulated turn-duration interval) and feeds each utterance through the
signal detector + nudge engine.

This satisfies the Q4 requirement:
  "recorded call replayed at real-time speed in chunks"

The replay engine:
  1. Reads a transcript JSON (Q1/Q3 format with 'dialogue' or 'turns' array)
  2. Computes inter-turn delay from timestamps (or uses a fixed default)
  3. Feeds utterances one-by-one with asyncio.sleep() to simulate real time
  4. Records T0–T4 timestamps via LatencyTracker
  5. Emits nudges via an async callback

IMPORTANT: Processing does NOT wait for the whole call to finish before
generating nudges — each turn is processed as it arrives, exactly as in
a live call.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from .signal_detector import SignalDetector
from .nudge_engine import NudgeEngine, Nudge
from .latency_tracker import LatencyTracker, LatencyRecord

logger = logging.getLogger(__name__)

# Simulated ASR latency range (ms) for replay mode
# In a live call this would be real Whisper/DeepSpeech latency
_ASR_LATENCY_MEAN_MS = 180.0
_ASR_LATENCY_JITTER_MS = 40.0

NudgeCallback = Callable[[Nudge, LatencyRecord], Coroutine[Any, Any, None]]


def _load_transcript(path: Path) -> List[Dict]:
    """Load dialogue turns from a Q1 or Q3 format transcript JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))

    # Q1 format: {"dialogue": [...]}
    if "dialogue" in data:
        return data["dialogue"]

    # Q3 format: {"turns": [...]} (used in Q3 ph/id recordings)
    if "turns" in data:
        return data["turns"]

    raise ValueError(f"Unknown transcript format in {path}: no 'dialogue' or 'turns' key")


def _compute_delays(turns: List[Dict], default_delay: float = 2.0) -> List[float]:
    """
    Compute per-turn delays from ISO timestamps if available,
    otherwise use default_delay seconds between turns.
    """
    delays = []
    for i, turn in enumerate(turns):
        if i == 0:
            delays.append(0.0)
            continue
        ts_prev = turns[i - 1].get("timestamp") or turns[i - 1].get("ts")
        ts_curr = turn.get("timestamp") or turn.get("ts")
        if ts_prev and ts_curr:
            try:
                from datetime import datetime, timezone
                def _parse(s: str):
                    s = s.replace("Z", "+00:00")
                    return datetime.fromisoformat(s)
                delta = (_parse(ts_curr) - _parse(ts_prev)).total_seconds()
                # Clamp: minimum 0.5s, maximum 5s for replay speed
                delays.append(max(0.5, min(delta, 5.0)))
            except Exception:
                delays.append(default_delay)
        else:
            delays.append(default_delay)
    return delays


class TranscriptReplayEngine:
    """
    Replay a transcript at real-time speed, generating live nudges per turn.

    Usage
    -----
    engine = TranscriptReplayEngine(transcript_path)
    await engine.run(nudge_callback=my_async_callback)
    stats = engine.latency_tracker.compute_stats()
    nudges = engine.nudge_engine.get_active_nudges()
    """

    def __init__(
        self,
        transcript_path: Path,
        confidence_threshold: float = 0.65,
        cooldown_seconds: float = 30.0,
        expiry_seconds: float = 60.0,
        max_repetitions: int = 3,
        replay_speed: float = 1.0,   # 1.0 = real time, 2.0 = 2x speed
    ):
        self.transcript_path = transcript_path
        self.replay_speed = replay_speed

        self.signal_detector = SignalDetector(confidence_threshold=confidence_threshold)
        self.nudge_engine = NudgeEngine(
            confidence_threshold=confidence_threshold,
            cooldown_seconds=cooldown_seconds,
            expiry_seconds=expiry_seconds,
            max_repetitions=max_repetitions,
        )
        self.latency_tracker = LatencyTracker()

        self._turns: List[Dict] = []
        self._delays: List[float] = []
        self._is_loaded = False

    def load(self) -> None:
        """Load transcript from file. Called automatically by run()."""
        self._turns = _load_transcript(self.transcript_path)
        self._delays = _compute_delays(self._turns)
        self._is_loaded = True
        logger.info(f"[Replay] Loaded {len(self._turns)} turns from {self.transcript_path.name}")

    async def run(
        self,
        nudge_callback: Optional[NudgeCallback] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[Nudge]:
        """
        Replay the transcript at real-time speed.

        Parameters
        ----------
        nudge_callback : async callable(nudge, latency_record) called for each new nudge
        progress_callback : sync callable(turn_index, total, speaker) for progress display

        Returns
        -------
        List of all Nudge objects generated during the replay.
        """
        if not self._is_loaded:
            self.load()

        all_nudges: list[Nudge] = []
        prev_agent_text: Optional[str] = None

        for i, turn in enumerate(self._turns):
            # Simulate real-time delay
            delay = self._delays[i] / self.replay_speed
            if delay > 0:
                await asyncio.sleep(delay)

            speaker = turn.get("speaker", "unknown")
            text = turn.get("text", "").strip()
            if not text:
                continue

            idx = turn.get("turn", i + 1)

            if progress_callback:
                progress_callback(i, len(self._turns), speaker)

            # ── T0: utterance received ─────────────────────────────────────
            rec = self.latency_tracker.new_record(idx, speaker, text)

            # ── T1: transcription complete (simulated ASR latency) ─────────
            # In live mode this would be actual Whisper transcription latency.
            # In replay mode we add a realistic simulated ASR delay.
            import random
            asr_ms = _ASR_LATENCY_MEAN_MS + random.uniform(
                -_ASR_LATENCY_JITTER_MS, _ASR_LATENCY_JITTER_MS
            )
            await asyncio.sleep(asr_ms / 1000.0)  # simulate ASR processing
            rec.t1_transcription_ms = time.time() * 1000

            # ── T2: signal detection ───────────────────────────────────────
            signals = self.signal_detector.detect(
                utterance=text,
                speaker=speaker,
                utterance_index=idx,
                agent_last_response=prev_agent_text,
            )
            rec.t2_signal_detected_ms = time.time() * 1000

            # ── T3: nudge generation ───────────────────────────────────────
            new_nudges = self.nudge_engine.process_signals(signals)
            rec.t3_nudge_generated_ms = time.time() * 1000
            rec.nudge_count = len(new_nudges)

            # ── T4: nudge delivery ─────────────────────────────────────────
            for nudge in new_nudges:
                if nudge_callback:
                    await nudge_callback(nudge, rec)
                all_nudges.append(nudge)

            rec.t4_nudge_delivered_ms = time.time() * 1000
            self.latency_tracker.finalize_record(rec)

            # Track previous agent text for context
            if speaker == "agent":
                prev_agent_text = text

        logger.info(
            f"[Replay] Completed: {len(self._turns)} turns, "
            f"{len(all_nudges)} nudges generated"
        )
        return all_nudges

    def get_summary(self) -> dict:
        """Return replay results summary."""
        return {
            "transcript":    self.transcript_path.name,
            "total_turns":   len(self._turns),
            "nudge_stats":   self.nudge_engine.get_stats(),
            "latency_stats": self.latency_tracker.compute_stats(),
            "nudges": [n.to_dict() for n in self.nudge_engine.get_active_nudges()],
            "all_nudges": [n.to_dict() for n in self.nudge_engine._all_nudges],
            "latency_records": [r.to_dict() for r in self.latency_tracker.get_records()],
        }
