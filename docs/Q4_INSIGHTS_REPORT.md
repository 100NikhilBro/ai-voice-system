# Q4 Live Insights / Nudges — Implementation Report

## Overview

Q4 implements a genuine real-time (or real-time-speed-replay) call-insights pipeline that analyzes a call while it is happening and produces short actionable nudges for an operator or supervisor.

> **Critical distinction**: The system processes utterances one-by-one with inter-turn delays matching the original call pacing. It is NOT post-call batch analysis.

---

## Architecture

```
Audio / Utterance
       │
       ▼ T0 (received)
  TranscriptReplayEngine / WebSocket handler
       │
       ▼ T1 (transcription completed)
  SignalDetector
       │  ─ intent_shift
       │  ─ compliance_risk
       │  ─ sentiment_negative
       │  ─ buying_signal
       │  ─ missed_opportunity
       │  ─ callback_needed
       ▼ T2 (signal detected)
  NudgeEngine (with all controls)
       │
       ▼ T3 (nudge generated)
  InsightSession → broadcast to subscribers
       │
       ▼ T4 (nudge delivered)
  WebSocket /ws/insights/{session_id}   ← live operator dashboard
  REST GET /api/v1/insights/nudges/{id} ← polling fallback
```

### Source Files

| File | Purpose |
|---|---|
| [`src/insights/signal_detector.py`](../src/insights/signal_detector.py) | 6-type keyword/regex signal classifier |
| [`src/insights/nudge_engine.py`](../src/insights/nudge_engine.py) | Nudge generator with all required controls |
| [`src/insights/latency_tracker.py`](../src/insights/latency_tracker.py) | T0–T4 capture and P50/P95 computation |
| [`src/insights/replay_engine.py`](../src/insights/replay_engine.py) | Real-time-speed transcript replay |
| [`src/insights/session.py`](../src/insights/session.py) | In-process live session + subscriber broadcast |
| [`src/api/insights_routes.py`](../src/api/insights_routes.py) | FastAPI WebSocket + REST endpoints |
| [`tests/test_q4_insights.py`](../tests/test_q4_insights.py) | 17 automated tests |
| [`scripts/run_q4_replay.py`](../scripts/run_q4_replay.py) | CLI replay runner with P50/P95 reporting |
| [`artifacts/q4_scenarios/`](../artifacts/q4_scenarios/) | 4 scenario transcripts + replay report |

---

## Real-Time / Replay Mode

### What "real-time-speed replay" means here

The `TranscriptReplayEngine` reads a saved transcript and feeds utterances to the pipeline **one at a time**, sleeping between turns to simulate the original call pacing:

```python
delay = inter_turn_seconds / replay_speed
await asyncio.sleep(delay)                 # simulate real-time gap
# ... simulate ASR latency (T0 → T1)
await asyncio.sleep(asr_ms / 1000.0)
signals = signal_detector.detect(text)    # T2
nudges  = nudge_engine.process(signals)   # T3
await broadcast_to_subscribers(nudges)    # T4
```

- Nudges are generated **as each turn arrives**, not after the call ends.
- The replay can be slowed (speed=1.0) or accelerated (speed=10.0) for testing.
- `replay_speed=1.0` reproduces exact original call timing.

### Live WebSocket Mode

For a truly live call, the operator dashboard connects to:
```
WS  ws://host/ws/insights/{session_id}
```

The call agent (or any caller) pushes utterances:
```json
{ "type": "utterance", "speaker": "customer", "text": "...", "t0_ms": 1234567.0 }
```

The server replies with nudges in real time:
```json
{
  "type": "nudge",
  "session_id": "abc123",
  "nudge": {
    "signal_type": "compliance_risk",
    "priority": "HIGH",
    "title": "Warning: Compliance Risk Detected",
    "action": "Correct agent: avoid guarantees...",
    "confidence": 0.90,
    "topic_group": "compliance"
  },
  "latency_so_far": 18.4
}
```

---

## Signal Types

| Signal | Speaker | Detection Method | Confidence Range |
|---|---|---|---|
| `compliance_risk` | agent | Regex: guarantee/no waiting period/off-the-record/100% covered | 0.80 – 0.95 |
| `sentiment_negative` | customer | Regex: explicit frustration, fraud accusation, cancellation | 0.65 – 0.95 |
| `buying_signal` | customer | Regex: application/enrollment intent, plan selection | 0.70 – 0.90 |
| `missed_opportunity` | customer | Regex: family/vehicle/property mention = cross-sell cue | 0.60 – 0.75 |
| `callback_needed` | customer | Regex: call-back request, deferral, "think about it" | 0.70 – 0.90 |
| `intent_shift` | any | Keyword: "actually"/"never mind"/"wait no" | 0.60 – 0.80 |

---

## Nudge Controls

All controls are configurable per session (via REST `POST /api/v1/insights/sessions` or constructor parameters):

| Control | Parameter | Default | Effect |
|---|---|---|---|
| Confidence threshold | `confidence_threshold` | 0.65 | Suppress signals below this score |
| Cooldown | `cooldown_seconds` | 30.0 | Same signal type won't re-fire within N seconds |
| Duplicate suppression | internal | always on | Same (type, evidence_key) pair fires at most once |
| Expiry | `expiry_seconds` | 60.0 | Nudge removed from active list after N seconds |
| Max repetitions | `max_repetitions` | 3 | Signal type silenced after N fires per session |
| Priority | per template | HIGH/MEDIUM/LOW | Used for dashboard ordering and filtering |
| Topic grouping | per template | compliance/sales/sentiment/follow_up/navigation | Groups nudges in dashboard by category |

---

## Four Required Scenario Verification

### Scenario 1: Missed Cross-Sell Opportunity

**File**: [`artifacts/q4_scenarios/scenario_01_cross_sell.json`](../artifacts/q4_scenarios/scenario_01_cross_sell.json)

**Customer trigger utterances**:
- Turn 4: *"My wife and two kids are also uninsured, but let's start with me."*  → `missed_opportunity` (conf=0.75, evidence: "family mention – group plan opportunity")
- Turn 8: *"I also have a car and my house — do you offer any other products?"* → `missed_opportunity` (conf=0.70, evidence: "property mention – home insurance opportunity")
- Turn 10: *"Sure, sounds interesting. How do I apply?"* → `buying_signal` (conf=0.70)

**Nudges generated**:
```
[MEDIUM] Cross-Sell Opportunity
Action: Customer mentioned family/assets — ask about group/family plan or additional coverage.
Confidence: 0.75

[HIGH] Buying Signal Detected
Action: Move to close: offer next steps — application form, advisor callback, or plan summary.
Confidence: 0.70
```

**Latency** (Scenario 1 actual): ASR P50=185.6ms, E2E P50=186.3ms

---

### Scenario 2: Skipped Disclosure / Risky Statement

**File**: [`artifacts/q4_scenarios/scenario_02_compliance_risk.json`](../artifacts/q4_scenarios/scenario_02_compliance_risk.json)

**Agent trigger utterances**:
- Turn 3: *"you are guaranteed coverage from day one"* → `compliance_risk` (conf=0.90, evidence: "guarantee claim")
- Turn 5: *"Don't worry about the disclosure... off the record"* → `compliance_risk` (conf=0.95, evidence: "off-the-record comment")
- Turn 7: *"You are 100% covered... no exclusions"* → `compliance_risk` (conf=0.90, evidence: "100% coverage claim")

**Nudges generated**:
```
[HIGH] Compliance Risk Detected
Action: Correct agent: avoid guarantees/non-compliant claims. Use verified KB language only.
Confidence: 0.90 / 0.95
```

**Note**: Multiple compliance violations in one call fire up to `max_repetitions` times (default 3), then silence. Each violation has a distinct evidence key so duplicate suppression does not prevent detection of genuinely new violations.

---

### Scenario 3: Rising Customer Frustration

**File**: [`artifacts/q4_scenarios/scenario_03_frustration.json`](../artifacts/q4_scenarios/scenario_03_frustration.json)

**Customer trigger utterances**:
- Turn 4: *"This is ridiculous — I paid premiums for two years... I'm not happy"* → `sentiment_negative` (conf=0.90)
- Turn 6: *"How long do I have to wait... complete waste of money... thinking about cancelling"*
- Turn 8: *"I am absolutely furious... This is a scam!"* → `sentiment_negative` (conf=0.95)

**Nudge generated** (first fire, then cooldown):
```
[HIGH] Customer Frustration Rising
Action: Acknowledge concern empathetically. Offer concrete resolution or supervisor escalation.
Confidence: 0.90
```

**Latency** (Scenario 3 actual): ASR P50=201.6ms, Signal Detection P50=0.2ms, E2E P50=201.8ms

---

### Scenario 4: Noisy / Ambiguous Call — Nudge Suppression

**File**: [`artifacts/q4_scenarios/scenario_04_noisy_no_nudge.json`](../artifacts/q4_scenarios/scenario_04_noisy_no_nudge.json)

**Customer utterances**: Fragmented, one-word, trailing-off, no clear signal content.

**Result**: No HIGH-priority false-positive nudges. Total nudge count ≤ 2.
- `callback_needed` (MEDIUM, conf=0.90) fires on turn 10 when customer says "call back later" — this is **correct behavior**, not a false positive. The customer is explicitly signaling they will not decide now.
- `intent_shift` (LOW, conf=0.65) fires on "never mind" — this is **expected**.
- No compliance, frustration, buying, or missed-opportunity nudges fire.

**False-positive verification**: 8 completely benign utterances (name, age, coverage interest, gold plan question, thanks) produce **zero signals** at production threshold (0.65).

---

## Measured Latency (Actual — from `run_q4_replay.py`)

All measurements from `python scripts/run_q4_replay.py` run at 5x replay speed, confidence=0.65.

### Aggregate Across All 4 Scenarios (39 turns)

| Metric | Value |
|---|---|
| Total turns processed | 39 |
| Total nudges generated | 6 |
| **End-to-End P50 (T0→T4)** | **186.0 ms** |
| **End-to-End P95 (T0→T4)** | **226.6 ms** |
| End-to-End max | 234.6 ms |

### Per-Component Latency Breakdown

| Stage | P50 | P95 | Mean | Notes |
|---|---|---|---|---|
| **T1-T0 ASR / Transcription** | ~185 ms | ~225 ms | ~190 ms | Simulated ASR (180ms ± 40ms jitter). In live mode this is real Whisper/cloud ASR latency. |
| **T2-T1 Signal Detection** | 0.2 ms | 1.4 ms | 0.4 ms | Pure Python regex; sub-millisecond. |
| **T3-T2 Nudge Generation** | 0.1 ms | 0.3 ms | 0.1 ms | Dictionary lookup + object creation. |
| **T4-T3 Delivery / Broadcast** | 0.1 ms | 0.2 ms | 0.1 ms | In-process async callback or WebSocket send. |
| **T0→T4 End-to-End** | 186 ms | 227 ms | 191 ms | Dominated by ASR latency. |

### Per-Scenario Summary

| Scenario | Turns | Nudges | ASR P50 | E2E P50 |
|---|---|---|---|---|
| Cross-sell opportunity | 11 | 2 | 185.6 ms | 186.3 ms |
| Compliance risk | 9 | 1 | 174.0 ms | 174.0 ms |
| Rising frustration | 9 | 1 | 201.6 ms | 201.8 ms |
| Noisy / suppressed | 10 | 2* | 182.4 ms | 182.6 ms |

\* Scenario 4 fires 2 nudges (MEDIUM callback + LOW intent-shift) from turn 10 only — no HIGH false positives.

> **Note on ASR latency**: In replay mode, ASR latency is simulated (Gaussian around 180ms ± 40ms) to represent realistic cloud/local Whisper transcription latency. In a fully live integration, T0 would be the audio chunk timestamp and T1 would be the actual transcription completion timestamp from the ASR provider.

---

## Nudge Delivery Mechanism

### Primary: WebSocket Live Stream

```
WS  /ws/insights/{session_id}
```

Operator dashboard connects and receives a stream of nudge events as they fire. Protocol documented in [`src/api/insights_routes.py`](../src/api/insights_routes.py).

### Secondary: REST Polling Fallback

```
POST /api/v1/insights/utterance    ← push one utterance, get nudges back synchronously
GET  /api/v1/insights/nudges/{id}  ← poll current active (non-expired) nudges
```

### Session Management

```
POST   /api/v1/insights/sessions           ← create session with config
GET    /api/v1/insights/sessions           ← list active sessions
GET    /api/v1/insights/sessions/{id}      ← session summary + latency stats
DELETE /api/v1/insights/sessions/{id}      ← close + final report
POST   /api/v1/insights/replay             ← replay saved transcript at real-time speed
```

---

## False-Positive Analysis

### Known false-positive risks

| Pattern | Risk | Mitigation |
|---|---|---|
| `"sounds good"` | Could fire on routine agreement | Requires "sounds good" without a purchase qualifier; confidence 0.70 (above default threshold) |
| `"callback_needed"` on "call me back later" in a noisy call | Actually *correct* — customer IS signaling deferral | Not suppressed; this is accurate detection |
| `"intent_shift"` on "actually" | Common filler word | Confidence 0.60, below production threshold of 0.65 — suppressed |
| `"missed_opportunity"` on agent mentioning family | False if agent, not customer | Rule restricted to `speaker == "customer"` |
| `"compliance_risk"` on customer text | False if customer says "you guarantee..." to confirm | Rule restricted to `speaker == "agent"` |

### Approximate false-positive rate (8 benign utterances)

- **0 signals / 0 nudges** on: name, age, health status, plan interest, room-rent question, closing thanks, standard agent greetings, plan recommendations.
- **Production threshold 0.65** ensures only high-confidence patterns fire.

### Known limitations

1. **ASR latency in replay is simulated** — actual latency depends on the ASR provider (Whisper Local ≈ 200–600ms, Azure/Google ≈ 100–300ms, real-time streaming ASR can be < 100ms per chunk).
2. **Detection is rule-based regex** — does not handle paraphrase variations not captured by current patterns. A production system would use a lightweight LLM classifier or a fine-tuned NLI model.
3. **No audio-level analysis** — signal detection operates on transcribed text, not raw audio. Tone, pitch, speaking rate are not captured.
4. **Cooldown across sessions** — the 30-second cooldown is session-scoped. If the same agent makes the same mistake in two calls, both calls will generate a nudge independently.
5. **No persistence** — nudge history and session summaries are in-memory only. A production system would persist to the same PostgreSQL+pgvector database used by Q1/Q2.

---

## Test Suite Summary

```
tests/test_q4_insights.py  — 17 tests, all passed
```

| Test | Verifies |
|---|---|
| `test_q4_scenario_cross_sell` | missed_opportunity + buying_signal nudges |
| `test_q4_scenario_cross_sell_latency` | T0–T4 monotonic timestamps, P50/P95 shape |
| `test_q4_scenario_compliance_risk` | HIGH compliance_risk nudge |
| `test_q4_scenario_compliance_risk_multiple_violations` | ≥2 distinct violations detected |
| `test_q4_scenario_frustration` | HIGH sentiment_negative nudge |
| `test_q4_scenario_frustration_individual_utterances` | Per-utterance detection |
| `test_q4_scenario_noisy_no_nudge` | No HIGH false positives, total ≤ 2 nudges |
| `test_q4_false_positive_analysis_benign_text` | Zero signals on 8 benign utterances |
| `test_q4_nudge_controls_cooldown` | Second fire within 30s suppressed |
| `test_q4_nudge_controls_duplicate_suppression` | Same evidence key fires once only |
| `test_q4_nudge_controls_expiry` | Expired nudges absent from active list |
| `test_q4_nudge_controls_max_repetitions` | Signal type silenced at max_rep=2 |
| `test_q4_latency_tracking` | T0–T4 set on all records, P50 ≥ 0, P95 ≥ P50 |
| `test_q4_replay_engine_real_time_speed` | Replay took > 50ms (not instant batch) |
| `test_q4_insight_session_api` | Session subscriber receives nudges via callback |
| `test_q4_buying_signal_detection` | 3 buying-intent utterances all detected |
| `test_q4_callback_detection` | 3 callback utterances all detected |

---

## Full Regression

```
python -m pytest -v
53 passed, 2 warnings in 28.96s
```

| Suite | Count | Result |
|---|---|---|
| Q1 API | 6 | PASSED |
| Q1 Ingestion | 5 | PASSED |
| Q1 PII | 6 | PASSED |
| Q1 Scenarios | 6 | PASSED |
| Q2 Benchmark | 1 | PASSED |
| Q2 Retrieval | 4 | PASSED |
| Q3 ASR | 2 | PASSED |
| Q3 Indonesia | 3 | PASSED |
| Q3 Philippines | 3 | PASSED |
| **Q4 Insights** | **17** | **PASSED** |
| **Total** | **53** | **0 failures** |
