"""
Latency Tracker
================
Captures T0–T4 timestamps per utterance and computes P50/P95 statistics.

  T0 = audio/utterance received
  T1 = transcription completed (for replay: T0 + simulated ASR latency)
  T2 = signal detected
  T3 = nudge generated
  T4 = nudge delivered/displayed

All times are epoch-milliseconds (float).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional
import statistics


@dataclass
class LatencyRecord:
    """One row of end-to-end latency for a single utterance processing cycle."""
    utterance_index: int
    speaker: str
    utterance_preview: str   # first 60 chars

    t0_audio_received_ms: float    = 0.0
    t1_transcription_ms:  float    = 0.0
    t2_signal_detected_ms: float   = 0.0
    t3_nudge_generated_ms: float   = 0.0
    t4_nudge_delivered_ms: float   = 0.0

    nudge_count: int = 0

    # ── derived latencies (ms) ─────────────────────────────────────────────

    @property
    def asr_latency_ms(self) -> float:
        """T1 – T0"""
        return max(0.0, self.t1_transcription_ms - self.t0_audio_received_ms)

    @property
    def signal_detection_latency_ms(self) -> float:
        """T2 – T1"""
        return max(0.0, self.t2_signal_detected_ms - self.t1_transcription_ms)

    @property
    def nudge_generation_latency_ms(self) -> float:
        """T3 – T2"""
        return max(0.0, self.t3_nudge_generated_ms - self.t2_signal_detected_ms)

    @property
    def delivery_latency_ms(self) -> float:
        """T4 – T3"""
        return max(0.0, self.t4_nudge_delivered_ms - self.t3_nudge_generated_ms)

    @property
    def end_to_end_latency_ms(self) -> float:
        """T4 – T0"""
        if self.t4_nudge_delivered_ms > 0 and self.t0_audio_received_ms > 0:
            return max(0.0, self.t4_nudge_delivered_ms - self.t0_audio_received_ms)
        return 0.0

    def to_dict(self) -> dict:
        return {
            "utterance_index":          self.utterance_index,
            "speaker":                  self.speaker,
            "utterance_preview":        self.utterance_preview,
            "t0_audio_received_ms":     round(self.t0_audio_received_ms, 2),
            "t1_transcription_ms":      round(self.t1_transcription_ms, 2),
            "t2_signal_detected_ms":    round(self.t2_signal_detected_ms, 2),
            "t3_nudge_generated_ms":    round(self.t3_nudge_generated_ms, 2),
            "t4_nudge_delivered_ms":    round(self.t4_nudge_delivered_ms, 2),
            "asr_latency_ms":           round(self.asr_latency_ms, 2),
            "signal_detection_latency_ms": round(self.signal_detection_latency_ms, 2),
            "nudge_generation_latency_ms": round(self.nudge_generation_latency_ms, 2),
            "delivery_latency_ms":      round(self.delivery_latency_ms, 2),
            "end_to_end_latency_ms":    round(self.end_to_end_latency_ms, 2),
            "nudge_count":              self.nudge_count,
        }


class LatencyTracker:
    """Collects LatencyRecords for a session and computes aggregate stats."""

    def __init__(self):
        self._records: List[LatencyRecord] = []

    def new_record(self, utterance_index: int, speaker: str, text: str) -> LatencyRecord:
        """Create a new record with T0 = now."""
        rec = LatencyRecord(
            utterance_index=utterance_index,
            speaker=speaker,
            utterance_preview=text[:60],
            t0_audio_received_ms=time.time() * 1000,
        )
        self._records.append(rec)
        return rec

    def finalize_record(self, rec: LatencyRecord) -> None:
        """Set T4 to now if not already set, closing the measurement."""
        if rec.t4_nudge_delivered_ms == 0.0:
            rec.t4_nudge_delivered_ms = time.time() * 1000

    def get_records(self) -> List[LatencyRecord]:
        return list(self._records)

    def _latencies_with_nudges(self) -> List[float]:
        """End-to-end latencies for turns that generated at least one nudge."""
        return [r.end_to_end_latency_ms for r in self._records if r.nudge_count > 0 and r.end_to_end_latency_ms > 0]

    def _all_e2e_latencies(self) -> List[float]:
        """All non-zero end-to-end latencies."""
        return [r.end_to_end_latency_ms for r in self._records if r.end_to_end_latency_ms > 0]

    @staticmethod
    def _percentile(data: List[float], p: float) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = (p / 100) * (len(sorted_data) - 1)
        lo = int(idx)
        hi = min(lo + 1, len(sorted_data) - 1)
        frac = idx - lo
        return sorted_data[lo] + frac * (sorted_data[hi] - sorted_data[lo])

    def compute_stats(self) -> dict:
        """
        Compute aggregate latency statistics across the session.
        Returns dict suitable for JSON serialization.
        """
        all_e2e = self._all_e2e_latencies()
        nudge_e2e = self._latencies_with_nudges()

        asr_lats =   [r.asr_latency_ms for r in self._records if r.asr_latency_ms > 0]
        sig_lats =   [r.signal_detection_latency_ms for r in self._records]
        nudge_lats = [r.nudge_generation_latency_ms for r in self._records if r.nudge_count > 0]
        deliv_lats = [r.delivery_latency_ms for r in self._records if r.nudge_count > 0]

        def summarize(data: List[float], label: str) -> dict:
            if not data:
                return {"label": label, "count": 0, "p50_ms": 0, "p95_ms": 0, "mean_ms": 0, "max_ms": 0}
            return {
                "label":   label,
                "count":   len(data),
                "p50_ms":  round(self._percentile(data, 50), 2),
                "p95_ms":  round(self._percentile(data, 95), 2),
                "mean_ms": round(statistics.mean(data), 2),
                "max_ms":  round(max(data), 2),
            }

        return {
            "session_turns":          len(self._records),
            "turns_with_nudges":      sum(1 for r in self._records if r.nudge_count > 0),
            "asr_latency":            summarize(asr_lats,   "ASR (T1-T0)"),
            "signal_detection":       summarize(sig_lats,   "Signal Detection (T2-T1)"),
            "nudge_generation":       summarize(nudge_lats, "Nudge Generation (T3-T2)"),
            "delivery_latency":       summarize(deliv_lats, "Delivery (T4-T3)"),
            "end_to_end_all_turns":   summarize(all_e2e,    "End-to-End All Turns (T4-T0)"),
            "end_to_end_nudge_turns": summarize(nudge_e2e,  "End-to-End Nudge Turns (T4-T0)"),
        }
