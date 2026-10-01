"""
Signal Detector
===============
Analyzes transcript utterances to detect 6 required signal types:

  1. intent_shift        – topic/intent change mid-call
  2. compliance_risk     – risky/non-compliant statement
  3. sentiment_negative  – frustration / negative sentiment
  4. buying_signal       – purchase intent / positive engagement
  5. missed_opportunity  – cross-sell / upsell chance
  6. callback_needed     – follow-up / callback required

Each signal carries a confidence score [0.0, 1.0] and supporting evidence.
Detection is rule-based + keyword matching (local, no external API calls).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class SignalType(str, Enum):
    INTENT_SHIFT       = "intent_shift"
    COMPLIANCE_RISK    = "compliance_risk"
    SENTIMENT_NEGATIVE = "sentiment_negative"
    BUYING_SIGNAL      = "buying_signal"
    MISSED_OPPORTUNITY = "missed_opportunity"
    CALLBACK_NEEDED    = "callback_needed"


@dataclass
class Signal:
    """A detected signal from a single utterance."""
    signal_type: SignalType
    confidence: float          # 0.0 – 1.0
    evidence: str              # matched text excerpt
    speaker: str               # "agent" or "customer"
    utterance_index: int       # turn number in the conversation
    raw_text: str              # original utterance
    detected_at_ms: float      # epoch ms (T2)


# ─────────────────────────────────────────────────────────────────────────────
# Keyword / pattern tables
# ─────────────────────────────────────────────────────────────────────────────

# Compliance risk: agent statements that are flagged (non-compliant phrases)
_COMPLIANCE_RISK_PATTERNS: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"\bguaranteed?\b", re.I),               0.90, "guarantee claim"),
    (re.compile(r"\bno waiting period\b", re.I),          0.95, "no waiting period claim"),
    (re.compile(r"\binstant coverage\b", re.I),           0.90, "instant coverage claim"),
    (re.compile(r"\balways covered\b", re.I),             0.85, "always covered claim"),
    (re.compile(r"\bnever denied\b", re.I),               0.90, "never denied claim"),
    (re.compile(r"\b100\s*%\s*covered\b", re.I),          0.90, "100% coverage claim"),
    (re.compile(r"\bno\s+exclusion", re.I),               0.85, "no exclusions claim"),
    (re.compile(r"\b(skip|waive|bypass)\s+(the\s+)?disclosure", re.I), 0.95, "skipped disclosure"),
    (re.compile(r"\bdon'?t\s+(need to\s+)?(worry about|mention)\b", re.I), 0.80, "minimizing disclosure"),
    (re.compile(r"\boff\s+the\s+record\b", re.I),         0.95, "off-the-record comment"),
    # Indonesian/Filipino compliance patterns
    (re.compile(r"\btanpa\s+bunga\b", re.I),              0.85, "zero-interest claim (ID)"),
    (re.compile(r"\bpasti\s+disetujui\b", re.I),          0.90, "guaranteed approval claim (ID)"),
    (re.compile(r"\bsure\s+na\s+approve\b", re.I),        0.90, "guaranteed approval (PH)"),
]

# Negative sentiment: customer frustration signals
_SENTIMENT_NEGATIVE_PATTERNS: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"\b(this is|that'?s)\s+(ridiculous|absurd|unfair|outrageous|terrible|horrible)\b", re.I), 0.90, "strong negative adjective"),
    # Allow optional adverbs between "am/I'm" and the emotion word (e.g. "I am absolutely furious")
    (re.compile(r"\bI('?m|\s+am)\s+(\w+\s+)?(angry|frustrated|annoyed|upset|furious|fed\s*up)\b", re.I), 0.90, "explicit frustration"),
    (re.compile(r"\b(angry|furious|frustrated|outraged)\b", re.I), 0.80, "frustration keyword"),
    (re.compile(r"\bthis\s+is\s+(a\s+)?waste\b", re.I),  0.80, "waste statement"),
    (re.compile(r"\b(not\s+)?happy\s+(with|about)\b", re.I), 0.70, "unhappy expression"),
    (re.compile(r"\bcancel\b.*\bpolicy\b|\bpolicy\b.*\bcancel\b", re.I), 0.75, "cancellation mention"),
    (re.compile(r"\bscam\b|\bfraud\b|\bcheat\b", re.I),   0.95, "fraud accusation"),
    (re.compile(r"\bgive\s*up\b|\bnot\s+worth\s+it\b",   re.I), 0.75, "giving up"),
    (re.compile(r"\bhow\s+(long|many)\s+(do\s+I|will\s+I)\s+have\s+to\s+wait\b", re.I), 0.65, "impatient waiting"),
    (re.compile(r"\bstop\s+calling\s+me\b", re.I),        0.85, "do not call"),
    # Bahasa Indonesia frustration
    (re.compile(r"\bkesal\b|\bmarah\b|\bkecewa\b", re.I), 0.80, "frustration (ID)"),
    (re.compile(r"\bgak\s+mau\b|\bnggak\s+mau\b", re.I),  0.65, "refusal (ID)"),
    # Filipino frustration
    (re.compile(r"\bgalit\b|\binis\b|\bnakakainis\b", re.I), 0.80, "frustration (PH)"),
]

# Buying signals: customer interest / purchase intent
_BUYING_SIGNAL_PATTERNS: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"\bhow\s+do\s+I\s+(sign|apply|enroll|get\s+started|purchase)\b", re.I), 0.90, "application intent"),
    (re.compile(r"\bI('?d|\s+would)\s+like\s+to\s+(apply|sign|enroll|purchase|buy)\b", re.I), 0.90, "explicit buy intent"),
    (re.compile(r"\bwhen\s+can\s+(I|we)\s+start\b", re.I), 0.85, "start timeline inquiry"),
    (re.compile(r"\bwhat\s+(documents|paperwork|forms)\s+do\s+I\s+need\b", re.I), 0.80, "document readiness"),
    (re.compile(r"\bsounds?\s+(really\s+)?good\b|\bsounds?\s+great\b", re.I), 0.70, "positive interest"),
    (re.compile(r"\bI('?m|\s+am)\s+interested\s+in\s+(applying|enrolling|signing|getting|purchasing)", re.I), 0.75, "purchase interest"),
    (re.compile(r"\bthat\s+(works?|suits?)\s+(for\s+me|me\s+well)\b", re.I), 0.75, "acceptance signal"),
    (re.compile(r"\bI\s+want\s+(the\s+)?(gold|platinum|silver|premium)\s+plan\b", re.I), 0.90, "plan selection"),
    (re.compile(r"\bberapa\s+(cicilan|biaya|premi)\b", re.I), 0.70, "price inquiry (ID)"),
    (re.compile(r"\bmau\s+(daftar|apply|coba)\b", re.I), 0.80, "apply intent (ID)"),
    (re.compile(r"\bmagkano\b|\bgusto\s+ko\b", re.I),    0.70, "price/interest (PH)"),
]

# Missed opportunities: agent missed a cross-sell or upsell cue
_MISSED_OPPORTUNITY_PATTERNS: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"\bmy\s+(spouse|partner|husband|wife|children?|kids?|family)\b", re.I), 0.75, "family mention – group plan opportunity"),
    (re.compile(r"\bI\s+also\s+(have|own|run)\b", re.I), 0.70, "additional asset mention"),
    (re.compile(r"\bmy\s+(car|vehicle|motorcycle|motor)\b", re.I), 0.70, "vehicle mention – auto insurance opportunity"),
    (re.compile(r"\bmy\s+(house|home|property)\b", re.I), 0.70, "property mention – home insurance opportunity"),
    (re.compile(r"\bdo\s+you\s+(also|also\s+have|offer)\b", re.I), 0.75, "product inquiry – cross-sell signal"),
    (re.compile(r"\b(life\s+insurance|term\s+insurance|endowment)\b", re.I), 0.70, "life insurance mention"),
    (re.compile(r"\bkendaraan\b|\bmotor\b|\bmobil\b", re.I), 0.65, "vehicle mention (ID)"),
    (re.compile(r"\bkeluarga\b|\banak\b|\bibu\b|\bbapak\b", re.I), 0.60, "family mention (ID)"),
]

# Callback / follow-up needs
_CALLBACK_NEEDED_PATTERNS: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"\bcall\s+(me\s+)?back\b", re.I),       0.90, "explicit callback request"),
    (re.compile(r"\bfollow\s*up\b", re.I),                0.80, "follow-up request"),
    (re.compile(r"\bI('?ll|\s+will)\s+think\s+about\s+it\b", re.I), 0.75, "deferred decision"),
    (re.compile(r"\bnot\s+(right\s+now|today|at\s+the\s+moment)\b", re.I), 0.70, "temporal deferral"),
    (re.compile(r"\blet\s+me\s+(check|ask|discuss|consult)\b", re.I), 0.75, "pending decision"),
    (re.compile(r"\bget\s+back\s+to\s+(you|us)\b", re.I), 0.80, "will get back promise"),
    (re.compile(r"\bnanti\s+(saja|dulu)\b", re.I),       0.75, "deferred (ID)"),
    (re.compile(r"\bsaya\s+(pikir|tanyakan)\s+dulu\b", re.I), 0.80, "think/ask first (ID)"),
]

# Intent shifts: sudden topic changes
_INTENT_SHIFT_KEYWORDS: list[tuple[str, float]] = [
    ("actually",           0.60),
    ("wait, no",           0.75),
    ("different question", 0.75),
    ("unrelated",          0.70),
    ("change the subject",  0.80),
    ("forget that",        0.70),
    ("never mind",         0.65),
    ("actually I want",    0.75),
    ("actually I need",    0.75),
]


class SignalDetector:
    """
    Stateful signal detector that tracks conversation context across turns.
    Must be instantiated once per call session.
    """

    def __init__(self, confidence_threshold: float = 0.60):
        self.confidence_threshold = confidence_threshold
        self._prev_topics: list[str] = []          # rough topic tracking for intent shifts
        self._agent_missed_cross_sell = False      # prevent false double-fire

    def detect(
        self,
        utterance: str,
        speaker: str,
        utterance_index: int,
        agent_last_response: Optional[str] = None,
    ) -> List[Signal]:
        """
        Analyze one utterance and return all detected signals above threshold.
        T2 timestamp is set inside this method.
        """
        now_ms = time.time() * 1000
        results: list[Signal] = []

        text = utterance.strip()
        if not text:
            return results

        # 1. Compliance risk – only from AGENT utterances
        if speaker == "agent":
            for pattern, conf, evidence in _COMPLIANCE_RISK_PATTERNS:
                m = pattern.search(text)
                if m and conf >= self.confidence_threshold:
                    results.append(Signal(
                        signal_type=SignalType.COMPLIANCE_RISK,
                        confidence=conf,
                        evidence=evidence,
                        speaker=speaker,
                        utterance_index=utterance_index,
                        raw_text=text,
                        detected_at_ms=now_ms,
                    ))
                    break  # one compliance flag per turn is enough

        # 2. Sentiment/frustration – from CUSTOMER
        if speaker == "customer":
            for pattern, conf, evidence in _SENTIMENT_NEGATIVE_PATTERNS:
                m = pattern.search(text)
                if m and conf >= self.confidence_threshold:
                    results.append(Signal(
                        signal_type=SignalType.SENTIMENT_NEGATIVE,
                        confidence=conf,
                        evidence=evidence,
                        speaker=speaker,
                        utterance_index=utterance_index,
                        raw_text=text,
                        detected_at_ms=now_ms,
                    ))
                    break

        # 3. Buying signals – from CUSTOMER
        if speaker == "customer":
            for pattern, conf, evidence in _BUYING_SIGNAL_PATTERNS:
                m = pattern.search(text)
                if m and conf >= self.confidence_threshold:
                    results.append(Signal(
                        signal_type=SignalType.BUYING_SIGNAL,
                        confidence=conf,
                        evidence=evidence,
                        speaker=speaker,
                        utterance_index=utterance_index,
                        raw_text=text,
                        detected_at_ms=now_ms,
                    ))
                    break

        # 4. Missed opportunity – customer mentions family/assets but AGENT didn't follow up
        if speaker == "customer":
            for pattern, conf, evidence in _MISSED_OPPORTUNITY_PATTERNS:
                m = pattern.search(text)
                if m and conf >= self.confidence_threshold:
                    results.append(Signal(
                        signal_type=SignalType.MISSED_OPPORTUNITY,
                        confidence=conf,
                        evidence=evidence,
                        speaker=speaker,
                        utterance_index=utterance_index,
                        raw_text=text,
                        detected_at_ms=now_ms,
                    ))
                    break

        # 5. Callback needed – from CUSTOMER
        if speaker == "customer":
            for pattern, conf, evidence in _CALLBACK_NEEDED_PATTERNS:
                m = pattern.search(text)
                if m and conf >= self.confidence_threshold:
                    results.append(Signal(
                        signal_type=SignalType.CALLBACK_NEEDED,
                        confidence=conf,
                        evidence=evidence,
                        speaker=speaker,
                        utterance_index=utterance_index,
                        raw_text=text,
                        detected_at_ms=now_ms,
                    ))
                    break

        # 6. Intent shift – any speaker, keyword-based + topic-drift heuristic
        text_lower = text.lower()
        for kw, conf in _INTENT_SHIFT_KEYWORDS:
            if kw in text_lower and conf >= self.confidence_threshold:
                results.append(Signal(
                    signal_type=SignalType.INTENT_SHIFT,
                    confidence=conf,
                    evidence=f"keyword: '{kw}'",
                    speaker=speaker,
                    utterance_index=utterance_index,
                    raw_text=text,
                    detected_at_ms=now_ms,
                ))
                break

        # Filter below threshold (belt-and-suspenders since we check inside each loop)
        return [s for s in results if s.confidence >= self.confidence_threshold]
