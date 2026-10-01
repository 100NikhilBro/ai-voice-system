"""
Nudge Engine
=============
Converts detected signals into short, actionable operator nudges.

Controls implemented:
  - confidence_threshold   – minimum signal confidence to generate a nudge
  - cooldown_seconds       – minimum gap between nudges of the SAME type
  - duplicate_suppression  – same (type, evidence) not re-fired within window
  - priority               – HIGH / MEDIUM / LOW ordering
  - expiry_seconds         – nudge expires from display after N seconds
  - max_repetitions        – nudge type silenced after this many fires
  - topic_grouping         – nudges grouped by topic for dashboard display
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from .signal_detector import Signal, SignalType


class NudgePriority(str, Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


@dataclass
class Nudge:
    """A single operator nudge."""
    nudge_id: str
    signal_type: SignalType
    priority: NudgePriority
    title: str                   # Short headline (≤ 60 chars)
    action: str                  # Actionable instruction for operator (≤ 140 chars)
    confidence: float            # Inherited from signal
    topic_group: str             # Grouping label
    utterance_index: int
    created_at_ms: float         # epoch ms (T3)
    expires_at_ms: float         # epoch ms after which nudge is stale
    evidence: str
    raw_text: str

    def is_expired(self, now_ms: Optional[float] = None) -> bool:
        now_ms = now_ms or time.time() * 1000
        return now_ms > self.expires_at_ms

    def to_dict(self) -> dict:
        return {
            "nudge_id":       self.nudge_id,
            "signal_type":    self.signal_type.value,
            "priority":       self.priority.value,
            "title":          self.title,
            "action":         self.action,
            "confidence":     round(self.confidence, 3),
            "topic_group":    self.topic_group,
            "utterance_index": self.utterance_index,
            "created_at_ms":  self.created_at_ms,
            "expires_at_ms":  self.expires_at_ms,
            "evidence":       self.evidence,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Nudge templates per signal type
# ─────────────────────────────────────────────────────────────────────────────

_NUDGE_TEMPLATES: Dict[SignalType, dict] = {
    SignalType.COMPLIANCE_RISK: {
        "priority":    NudgePriority.HIGH,
        "topic_group": "compliance",
        "title":       "⚠️ Compliance Risk Detected",
        "action":      "Correct agent: avoid guarantees/non-compliant claims. Use verified KB language only.",
    },
    SignalType.SENTIMENT_NEGATIVE: {
        "priority":    NudgePriority.HIGH,
        "topic_group": "sentiment",
        "title":       "😤 Customer Frustration Rising",
        "action":      "Acknowledge concern empathetically. Offer concrete resolution or supervisor escalation.",
    },
    SignalType.BUYING_SIGNAL: {
        "priority":    NudgePriority.HIGH,
        "topic_group": "sales",
        "title":       "🟢 Buying Signal Detected",
        "action":      "Move to close: offer next steps — application form, advisor callback, or plan summary.",
    },
    SignalType.MISSED_OPPORTUNITY: {
        "priority":    NudgePriority.MEDIUM,
        "topic_group": "sales",
        "title":       "💡 Cross-Sell Opportunity",
        "action":      "Customer mentioned family/assets — ask about group/family plan or additional coverage.",
    },
    SignalType.CALLBACK_NEEDED: {
        "priority":    NudgePriority.MEDIUM,
        "topic_group": "follow_up",
        "title":       "📅 Schedule Follow-Up",
        "action":      "Customer is deferring. Offer specific callback time slot and send summary email.",
    },
    SignalType.INTENT_SHIFT: {
        "priority":    NudgePriority.LOW,
        "topic_group": "navigation",
        "title":       "🔄 Topic Shift Detected",
        "action":      "Acknowledge new topic, address it, then guide back to qualification if appropriate.",
    },
}


class NudgeEngine:
    """
    Stateful nudge engine. One instance per call session.

    Parameters
    ----------
    confidence_threshold : float
        Minimum signal confidence to generate any nudge. Default 0.65.
    cooldown_seconds : float
        Minimum seconds between nudges of the same signal type. Default 30.
    expiry_seconds : float
        How long a nudge stays active before expiry. Default 60.
    max_repetitions : int
        How many times a signal type can fire before being silenced. Default 3.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.65,
        cooldown_seconds: float = 30.0,
        expiry_seconds: float = 60.0,
        max_repetitions: int = 3,
    ):
        self.confidence_threshold = confidence_threshold
        self.cooldown_seconds = cooldown_seconds
        self.expiry_seconds = expiry_seconds
        self.max_repetitions = max_repetitions

        # last fire time per signal type
        self._last_fired: Dict[SignalType, float] = {}
        # fire counts per signal type
        self._fire_counts: Dict[SignalType, int] = {}
        # set of (type, evidence) pairs to suppress duplicates
        self._seen_evidence: set[tuple] = set()
        # all nudges generated this session
        self._all_nudges: List[Nudge] = []

    def process_signals(self, signals: List[Signal]) -> List[Nudge]:
        """
        Convert a list of signals from one utterance into nudges,
        applying all controls. Returns only NEW nudges generated.
        """
        now_ms = time.time() * 1000
        new_nudges: list[Nudge] = []

        # Sort by priority: HIGH first
        _priority_order = {NudgePriority.HIGH: 0, NudgePriority.MEDIUM: 1, NudgePriority.LOW: 2}

        for signal in sorted(signals, key=lambda s: _priority_order.get(
            _NUDGE_TEMPLATES[s.signal_type]["priority"], 2
        )):
            # 1. Confidence threshold
            if signal.confidence < self.confidence_threshold:
                continue

            stype = signal.signal_type

            # 2. Max repetitions gate
            if self._fire_counts.get(stype, 0) >= self.max_repetitions:
                continue

            # 3. Cooldown gate
            last = self._last_fired.get(stype, 0.0)
            elapsed = (now_ms - last) / 1000.0  # seconds
            if elapsed < self.cooldown_seconds:
                continue

            # 4. Duplicate suppression (same type + same evidence key)
            evidence_key = (stype, signal.evidence[:50])
            if evidence_key in self._seen_evidence:
                continue

            # All gates passed – generate nudge
            template = _NUDGE_TEMPLATES[stype]
            expires_ms = now_ms + (self.expiry_seconds * 1000)

            nudge = Nudge(
                nudge_id=str(uuid.uuid4())[:8],
                signal_type=stype,
                priority=template["priority"],
                title=template["title"],
                action=template["action"],
                confidence=signal.confidence,
                topic_group=template["topic_group"],
                utterance_index=signal.utterance_index,
                created_at_ms=now_ms,
                expires_at_ms=expires_ms,
                evidence=signal.evidence,
                raw_text=signal.raw_text,
            )

            # Update state
            self._last_fired[stype] = now_ms
            self._fire_counts[stype] = self._fire_counts.get(stype, 0) + 1
            self._seen_evidence.add(evidence_key)
            self._all_nudges.append(nudge)
            new_nudges.append(nudge)

        return new_nudges

    def get_active_nudges(self, now_ms: Optional[float] = None) -> List[Nudge]:
        """Return non-expired nudges, sorted by priority."""
        now_ms = now_ms or time.time() * 1000
        _priority_order = {NudgePriority.HIGH: 0, NudgePriority.MEDIUM: 1, NudgePriority.LOW: 2}
        active = [n for n in self._all_nudges if not n.is_expired(now_ms)]
        return sorted(active, key=lambda n: _priority_order.get(n.priority, 2))

    def get_stats(self) -> dict:
        """Return session-level nudge statistics."""
        return {
            "total_nudges_generated": len(self._all_nudges),
            "fire_counts":            {k.value: v for k, v in self._fire_counts.items()},
            "active_nudges":          len(self.get_active_nudges()),
        }
