"""
Q4 Live Insights — Automated Test Suite
=========================================
Tests all four required scenarios plus nudge controls, latency tracking,
and false-positive analysis.

Test coverage:
  1. test_q4_scenario_cross_sell            – missed cross-sell opportunity
  2. test_q4_scenario_compliance_risk       – skipped disclosure / risky statement
  3. test_q4_scenario_frustration           – rising customer frustration
  4. test_q4_scenario_noisy_no_nudge        – noisy call, nudges should be suppressed
  5. test_q4_nudge_controls_cooldown        – cooldown prevents rapid re-fire
  6. test_q4_nudge_controls_duplicate       – duplicate suppression works
  7. test_q4_nudge_controls_expiry          – expired nudges not returned as active
  8. test_q4_nudge_controls_max_repetitions – max repetitions silences signal type
  9. test_q4_latency_tracking               – T0-T4 timestamps and P50/P95 calculation
  10. test_q4_false_positive_analysis       – benign text generates no signals
  11. test_q4_replay_engine_real_time_speed – replay processes turns with delays (live mode)
  12. test_q4_insight_session_api           – session create/push/summarize API
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

# ── Module imports ────────────────────────────────────────────────────────────
from src.insights.signal_detector import SignalDetector, SignalType
from src.insights.nudge_engine import NudgeEngine, NudgePriority
from src.insights.latency_tracker import LatencyTracker
from src.insights.replay_engine import TranscriptReplayEngine
from src.insights.session import InsightSession

SCENARIOS_DIR = Path(__file__).parent.parent / "artifacts" / "q4_scenarios"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def run(coro):
    """Run a coroutine synchronously (compatible with Python 3.14 where
    get_event_loop() raises RuntimeError on main thread if no loop exists)."""
    return asyncio.run(coro)



def _replay_scenario(filename: str, cooldown: float = 0.0, confidence: float = 0.60):
    """Replay a Q4 scenario JSON at maximum speed and return (nudges, summary)."""
    path = SCENARIOS_DIR / filename
    engine = TranscriptReplayEngine(
        transcript_path=path,
        confidence_threshold=confidence,
        cooldown_seconds=cooldown,
        expiry_seconds=300.0,
        max_repetitions=10,
        replay_speed=100.0,   # 100x speed = instant for tests
    )
    nudges = run(engine.run())
    return nudges, engine.get_summary()


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 1: Missed Cross-Sell Opportunity
# ─────────────────────────────────────────────────────────────────────────────

def test_q4_scenario_cross_sell():
    """
    Customer mentions spouse/children and vehicle/house.
    Expects: MISSED_OPPORTUNITY and/or BUYING_SIGNAL nudges.
    Verifies: nudge is actionable, confidence-aware, tied to conversation.
    """
    nudges, summary = _replay_scenario("scenario_01_cross_sell.json")

    signal_types = {n["signal_type"] for n in summary["all_nudges"]}
    print(f"\n[Scenario 1] Signal types detected: {signal_types}")
    print(f"[Scenario 1] Nudges generated: {len(summary['all_nudges'])}")
    for n in summary["all_nudges"]:
        print(f"  [{n['priority']}] {n['title']} | conf={n['confidence']:.2f} | action={n['action']}")

    # Must detect at least one missed opportunity or buying signal
    assert "missed_opportunity" in signal_types or "buying_signal" in signal_types, (
        f"Expected missed_opportunity or buying_signal, got: {signal_types}"
    )

    # Verify nudge properties
    for n in summary["all_nudges"]:
        assert len(n["title"]) <= 80, f"Title too long: {n['title']}"
        assert len(n["action"]) <= 200, f"Action too long: {n['action']}"
        assert 0.0 <= n["confidence"] <= 1.0
        assert n["priority"] in ("HIGH", "MEDIUM", "LOW")
        assert n["topic_group"] in ("sales", "compliance", "sentiment", "follow_up", "navigation")

    # Verify latency measurements exist
    stats = summary["latency_stats"]
    assert stats["session_turns"] > 0
    assert "signal_detection" in stats
    assert stats["signal_detection"]["p50_ms"] >= 0


def test_q4_scenario_cross_sell_latency():
    """Verify that all T0–T4 timestamps are captured and end-to-end latency is measured."""
    path = SCENARIOS_DIR / "scenario_01_cross_sell.json"
    engine = TranscriptReplayEngine(
        transcript_path=path,
        confidence_threshold=0.60,
        cooldown_seconds=0.0,
        expiry_seconds=300.0,
        max_repetitions=10,
        replay_speed=100.0,
    )
    run(engine.run())
    records = engine.latency_tracker.get_records()

    assert len(records) >= 5, "Should have at least 5 latency records"

    for rec in records:
        assert rec.t0_audio_received_ms > 0, "T0 must be set"
        assert rec.t1_transcription_ms > 0, "T1 must be set"
        assert rec.t2_signal_detected_ms > 0, "T2 must be set"
        assert rec.t3_nudge_generated_ms > 0, "T3 must be set"
        assert rec.t4_nudge_delivered_ms > 0, "T4 must be set"
        # T timestamps must be monotonically non-decreasing
        assert rec.t1_transcription_ms >= rec.t0_audio_received_ms
        assert rec.t2_signal_detected_ms >= rec.t1_transcription_ms
        assert rec.t3_nudge_generated_ms >= rec.t2_signal_detected_ms
        assert rec.t4_nudge_delivered_ms >= rec.t3_nudge_generated_ms

    stats = engine.latency_tracker.compute_stats()
    # P50 and P95 must be computable (or zero if no nudge turns)
    for key in ("asr_latency", "signal_detection", "end_to_end_all_turns"):
        assert key in stats, f"Missing stat: {key}"
        assert "p50_ms" in stats[key]
        assert "p95_ms" in stats[key]


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 2: Compliance Risk
# ─────────────────────────────────────────────────────────────────────────────

def test_q4_scenario_compliance_risk():
    """
    Agent makes guarantee/non-disclosure statements.
    Expects: HIGH priority COMPLIANCE_RISK nudge.
    """
    nudges, summary = _replay_scenario("scenario_02_compliance_risk.json")

    signal_types = {n["signal_type"] for n in summary["all_nudges"]}
    print(f"\n[Scenario 2] Signal types detected: {signal_types}")
    for n in summary["all_nudges"]:
        print(f"  [{n['priority']}] {n['title']} | conf={n['confidence']:.2f} | evidence={n['evidence']}")

    assert "compliance_risk" in signal_types, (
        f"Expected compliance_risk, got: {signal_types}"
    )

    # Compliance nudges must be HIGH priority
    compliance_nudges = [n for n in summary["all_nudges"] if n["signal_type"] == "compliance_risk"]
    assert all(n["priority"] == "HIGH" for n in compliance_nudges), (
        "All compliance nudges must be HIGH priority"
    )

    # Compliance nudge must have confidence >= 0.80
    assert all(n["confidence"] >= 0.80 for n in compliance_nudges), (
        "Compliance nudge confidence must be ≥ 0.80"
    )


def test_q4_scenario_compliance_risk_multiple_violations():
    """Agent makes multiple violations — verify at least 2 compliance signals detected."""
    detector = SignalDetector(confidence_threshold=0.60)

    violations = [
        ("agent", "Yes, you are guaranteed coverage from day one with no waiting period!"),
        ("agent", "Don't worry about the disclosure, just tick no for pre-existing conditions."),
        ("agent", "This is off the record — you are 100% covered, no exclusions apply."),
    ]

    all_signals = []
    for i, (speaker, text) in enumerate(violations):
        signals = detector.detect(text, speaker, i + 1)
        compliance = [s for s in signals if s.signal_type == SignalType.COMPLIANCE_RISK]
        all_signals.extend(compliance)
        print(f"  Turn {i+1}: {len(compliance)} compliance signals from: {text[:60]}")

    assert len(all_signals) >= 2, (
        f"Expected at least 2 compliance signals across 3 violations, got {len(all_signals)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 3: Rising Frustration
# ─────────────────────────────────────────────────────────────────────────────

def test_q4_scenario_frustration():
    """
    Customer expresses escalating frustration, cancellation threat, fraud accusation.
    Expects: SENTIMENT_NEGATIVE nudge with HIGH priority.
    """
    nudges, summary = _replay_scenario("scenario_03_frustration.json")

    signal_types = {n["signal_type"] for n in summary["all_nudges"]}
    print(f"\n[Scenario 3] Signal types detected: {signal_types}")
    for n in summary["all_nudges"]:
        print(f"  [{n['priority']}] {n['title']} | conf={n['confidence']:.2f} | evidence={n['evidence']}")

    assert "sentiment_negative" in signal_types, (
        f"Expected sentiment_negative, got: {signal_types}"
    )

    sentiment_nudges = [n for n in summary["all_nudges"] if n["signal_type"] == "sentiment_negative"]
    assert all(n["priority"] == "HIGH" for n in sentiment_nudges), (
        "Sentiment nudges must be HIGH priority"
    )


def test_q4_scenario_frustration_individual_utterances():
    """Verify individual frustration utterances are detected correctly."""
    detector = SignalDetector(confidence_threshold=0.60)

    frustration_utterances = [
        "This is ridiculous, I paid premiums for two years!",
        "I am absolutely furious with this company.",
        "This is a complete scam — I want to cancel my policy.",
    ]

    for i, text in enumerate(frustration_utterances):
        signals = detector.detect(text, "customer", i + 1)
        neg_signals = [s for s in signals if s.signal_type == SignalType.SENTIMENT_NEGATIVE]
        assert len(neg_signals) >= 1, (
            f"Expected sentiment_negative for: {text!r}, got signals: {[s.signal_type for s in signals]}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 4: Noisy Call — Nudge Suppression
# ─────────────────────────────────────────────────────────────────────────────

def test_q4_scenario_noisy_no_nudge():
    """
    Noisy/ambiguous/fragmented call should NOT generate nudges.
    Verifies false-positive suppression.
    """
    nudges, summary = _replay_scenario(
        "scenario_04_noisy_no_nudge.json",
        cooldown=0.0,
        confidence=0.65,   # Standard production threshold
    )

    print(f"\n[Scenario 4] Total nudges generated: {len(summary['all_nudges'])}")
    for n in summary["all_nudges"]:
        print(f"  [{n['priority']}] {n['title']} | conf={n['confidence']:.2f} | evidence={n['evidence']}")

    # The only nudges allowed in a purely noisy ambiguous call are:
    #   - intent_shift (very noisy text with 'actually'/'never mind') — LOW priority only
    # HIGH priority signals (compliance_risk, sentiment_negative) must NOT fire
    # Buying signals must NOT fire (no purchase intent)
    # Missed opportunity must NOT fire
    # Note: callback_needed may fire if customer literally says 'call back' — that is correct
    #       behavior and NOT a false positive. In a truly ambiguous call with no such phrase,
    #       it should not fire. We verify HIGH-priority false positives only.
    high_priority_false_positives = [
        n for n in summary["all_nudges"]
        if n["signal_type"] in {"compliance_risk", "sentiment_negative", "buying_signal", "missed_opportunity"}
        and n["priority"] == "HIGH"
    ]

    assert len(high_priority_false_positives) == 0, (
        f"HIGH-priority false-positive nudges detected in noisy scenario: "
        f"{[(n['signal_type'], n['evidence']) for n in high_priority_false_positives]}"
    )

    # Additionally: total nudge count should be very low (≤ 2)
    assert len(summary["all_nudges"]) <= 2, (
        f"Too many nudges ({len(summary['all_nudges'])}) in noisy/ambiguous call. "
        f"Suggest raising confidence threshold. Nudges: {[(n['signal_type'], n['evidence']) for n in summary['all_nudges']]}"
    )


def test_q4_false_positive_analysis_benign_text():
    """
    Verifies that completely benign customer utterances do not trigger any signals.
    This is the false-positive analysis test.
    """
    detector = SignalDetector(confidence_threshold=0.65)

    benign_utterances = [
        ("customer", "My name is Sarah and I'm 40 years old."),
        ("customer", "I don't have any pre-existing conditions."),
        ("customer", "I want to learn about hospitalization coverage options."),
        ("customer", "What is the room rent limit for the Gold plan?"),
        ("customer", "Thank you very much, that was very helpful."),
        ("agent",    "Lovely to meet you, Sarah! Let me help you find the right plan."),
        ("agent",    "At 40, you're eligible for all our main plan tiers."),
        ("agent",    "Based on your needs, the Gold plan may be suitable for you."),
    ]

    all_signals = []
    for i, (speaker, text) in enumerate(benign_utterances):
        signals = detector.detect(text, speaker, i + 1)
        all_signals.extend(signals)
        if signals:
            print(f"  [FALSE POSITIVE] Turn {i+1} ({speaker}): {text!r}")
            for s in signals:
                print(f"    → {s.signal_type} (conf={s.confidence:.2f}, evidence={s.evidence})")

    assert len(all_signals) == 0, (
        f"False-positive signals on benign utterances: "
        f"{[(s.signal_type.value, s.evidence) for s in all_signals]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Nudge Controls
# ─────────────────────────────────────────────────────────────────────────────

def test_q4_nudge_controls_cooldown():
    """Same signal type fired twice rapidly — second should be suppressed by cooldown."""
    engine = NudgeEngine(
        confidence_threshold=0.60,
        cooldown_seconds=30.0,
        expiry_seconds=120.0,
        max_repetitions=5,
    )
    detector = SignalDetector(confidence_threshold=0.60)

    text = "I am absolutely furious with this service."
    signals1 = detector.detect(text, "customer", 1)
    nudges1 = engine.process_signals(signals1)

    signals2 = detector.detect(text, "customer", 2)
    nudges2 = engine.process_signals(signals2)

    print(f"\n[Cooldown] First fire: {len(nudges1)} nudges, Second fire: {len(nudges2)} nudges")

    assert len(nudges1) >= 1, "First fire should produce a nudge"
    assert len(nudges2) == 0, "Second fire within cooldown should be suppressed"


def test_q4_nudge_controls_duplicate_suppression():
    """Same evidence key should not produce duplicate nudges."""
    engine = NudgeEngine(
        confidence_threshold=0.60,
        cooldown_seconds=0.0,  # no cooldown
        expiry_seconds=120.0,
        max_repetitions=5,
    )
    detector = SignalDetector(confidence_threshold=0.60)

    text = "I am absolutely furious."
    signals = detector.detect(text, "customer", 1)
    nudges1 = engine.process_signals(signals)

    # Re-fire same signals with same evidence key
    nudges2 = engine.process_signals(signals)

    print(f"\n[Duplicate] First fire: {len(nudges1)}, Duplicate attempt: {len(nudges2)}")

    assert len(nudges1) >= 1
    assert len(nudges2) == 0, "Duplicate same-evidence nudge must be suppressed"


def test_q4_nudge_controls_expiry():
    """Nudges beyond their expiry time should not appear in active nudges."""
    engine = NudgeEngine(
        confidence_threshold=0.60,
        cooldown_seconds=0.0,
        expiry_seconds=0.001,  # expire in 1ms
        max_repetitions=5,
    )
    detector = SignalDetector(confidence_threshold=0.60)

    text = "I am absolutely furious."
    signals = detector.detect(text, "customer", 1)
    nudges = engine.process_signals(signals)

    assert len(nudges) >= 1, "Should generate nudge"

    # Wait for expiry
    time.sleep(0.05)

    active = engine.get_active_nudges()
    print(f"\n[Expiry] Generated {len(nudges)}, Active after expiry: {len(active)}")
    assert len(active) == 0, "All nudges should have expired"


def test_q4_nudge_controls_max_repetitions():
    """Signal type is silenced after max_repetitions fires."""
    engine = NudgeEngine(
        confidence_threshold=0.60,
        cooldown_seconds=0.0,
        expiry_seconds=300.0,
        max_repetitions=2,
    )
    detector = SignalDetector(confidence_threshold=0.60)

    frustration_texts = [
        "I am absolutely furious with this!",
        "This service is terrible and ridiculous!",
        "I'm fed up with this company completely!",
    ]

    total_generated = 0
    for i, text in enumerate(frustration_texts):
        signals = detector.detect(text, "customer", i + 1)
        nudges = engine.process_signals(signals)
        total_generated += len(nudges)
        print(f"  Turn {i+1}: {len(nudges)} nudges (evidence reset from dup check)")

    # Due to duplicate suppression + max_repetitions=2, at most 2 sentiment nudges allowed
    sentiment_count = engine._fire_counts.get(from_insights_signal("sentiment_negative"), 0)
    print(f"\n[MaxRep] Total sentiment fires: {sentiment_count} (max_repetitions=2)")
    assert sentiment_count <= 2, f"Should not exceed max_repetitions=2, got {sentiment_count}"


def from_insights_signal(name: str):
    """Helper to get SignalType enum by value."""
    return SignalType(name)


# ─────────────────────────────────────────────────────────────────────────────
# Latency Tracking
# ─────────────────────────────────────────────────────────────────────────────

def test_q4_latency_tracking():
    """
    Verify T0–T4 capture and P50/P95 computation across multiple turns.
    """
    tracker = LatencyTracker()

    # Simulate 10 turns with known latencies
    for i in range(10):
        rec = tracker.new_record(i + 1, "customer", f"Test utterance {i}")
        time.sleep(0.01)
        rec.t1_transcription_ms = time.time() * 1000
        time.sleep(0.002)
        rec.t2_signal_detected_ms = time.time() * 1000
        time.sleep(0.001)
        rec.t3_nudge_generated_ms = time.time() * 1000
        if i % 2 == 0:  # simulate nudge on every other turn
            rec.nudge_count = 1
        tracker.finalize_record(rec)

    stats = tracker.compute_stats()

    print(f"\n[Latency] Stats:")
    print(f"  ASR P50: {stats['asr_latency']['p50_ms']:.2f}ms  P95: {stats['asr_latency']['p95_ms']:.2f}ms")
    print(f"  Signal detection P50: {stats['signal_detection']['p50_ms']:.2f}ms")
    print(f"  E2E all turns P50: {stats['end_to_end_all_turns']['p50_ms']:.2f}ms")

    assert stats["session_turns"] == 10
    assert stats["asr_latency"]["count"] == 10
    assert stats["asr_latency"]["p50_ms"] >= 0
    assert stats["asr_latency"]["p95_ms"] >= stats["asr_latency"]["p50_ms"]
    assert stats["end_to_end_all_turns"]["p50_ms"] >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Replay Engine — Real-Time Speed Verification
# ─────────────────────────────────────────────────────────────────────────────

def test_q4_replay_engine_real_time_speed():
    """
    Verify that the replay engine processes turns with inter-turn delays
    (not all-at-once post-call analysis). Uses replay_speed=50x for test speed.
    """
    path = SCENARIOS_DIR / "scenario_01_cross_sell.json"
    engine = TranscriptReplayEngine(
        transcript_path=path,
        confidence_threshold=0.60,
        cooldown_seconds=0.0,
        expiry_seconds=300.0,
        max_repetitions=10,
        replay_speed=50.0,  # fast but not instant
    )

    nudge_timestamps: list[float] = []

    async def on_nudge(nudge, rec):
        nudge_timestamps.append(time.time())

    start = time.time()
    nudges = run(engine.run(nudge_callback=on_nudge))
    elapsed = time.time() - start

    print(f"\n[Replay] Elapsed: {elapsed:.3f}s, Turns: {len(engine._turns)}, Nudges: {len(nudges)}")

    # Should have taken SOME time (not instant) — at 50x speed with 11 turns and ~2s avg gap
    # minimum real time = (11 * 0.5s delay / 50) + (11 * 180ms ASR / 50) ≈ ~0.11s minimum
    assert elapsed >= 0.05, f"Replay was too fast ({elapsed:.3f}s) — not simulating real time"

    # All latency records should have increasing t0 timestamps
    records = engine.latency_tracker.get_records()
    t0s = [r.t0_audio_received_ms for r in records]
    assert all(t0s[i] <= t0s[i+1] for i in range(len(t0s)-1)), (
        "T0 timestamps must be monotonically non-decreasing (real-time replay)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Insight Session API
# ─────────────────────────────────────────────────────────────────────────────

def test_q4_insight_session_api():
    """Test InsightSession API: process utterances, subscribe, and get summary."""
    session = InsightSession(
        session_id="test-q4-session",
        confidence_threshold=0.60,
        cooldown_seconds=0.0,
        expiry_seconds=120.0,
        max_repetitions=5,
    )

    received_nudges: list[dict] = []

    async def subscriber(msg: dict):
        if msg.get("type") == "nudge":
            received_nudges.append(msg["nudge"])

    session.subscribe(subscriber)

    async def run_session():
        # Turn 1: buying signal
        await session.process_utterance(
            "How do I apply for the Gold plan?",
            "customer"
        )
        # Turn 2: compliance risk
        await session.process_utterance(
            "Yes, you are guaranteed coverage with no waiting period at all.",
            "agent"
        )
        # Turn 3: callback
        await session.process_utterance(
            "Let me think about it and call you back.",
            "customer"
        )

    run(run_session())

    summary = session.get_summary()

    print(f"\n[Session] Nudges received via subscriber: {len(received_nudges)}")
    print(f"[Session] Total nudges in engine: {summary['nudge_stats']['total_nudges_generated']}")
    for n in summary["active_nudges"]:
        print(f"  [{n['priority']}] {n['title']}")

    assert summary["turn_index"] == 3
    assert summary["nudge_stats"]["total_nudges_generated"] >= 1
    # Subscriber should have received the same nudges
    assert len(received_nudges) >= 1


def test_q4_buying_signal_detection():
    """Standalone buying signal detection test."""
    detector = SignalDetector(confidence_threshold=0.60)

    buying_texts = [
        "How do I sign up for the Gold plan?",
        "I would like to apply for health insurance.",
        "That sounds great — when can I start?",
    ]

    for i, text in enumerate(buying_texts):
        signals = detector.detect(text, "customer", i + 1)
        buy_signals = [s for s in signals if s.signal_type == SignalType.BUYING_SIGNAL]
        print(f"  '{text[:50]}...' → {len(buy_signals)} buying signal(s)")
        assert len(buy_signals) >= 1, f"Expected BUYING_SIGNAL for: {text!r}"


def test_q4_callback_detection():
    """Callback/follow-up signal detection test."""
    detector = SignalDetector(confidence_threshold=0.60)

    callback_texts = [
        "Please call me back tomorrow.",
        "I'll think about it and get back to you.",
        "Not right now, let me discuss with my wife first.",
    ]

    for i, text in enumerate(callback_texts):
        signals = detector.detect(text, "customer", i + 1)
        cb_signals = [s for s in signals if s.signal_type == SignalType.CALLBACK_NEEDED]
        print(f"  '{text[:50]}' → {len(cb_signals)} callback signal(s)")
        assert len(cb_signals) >= 1, f"Expected CALLBACK_NEEDED for: {text!r}"
