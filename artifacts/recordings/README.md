# Q1 Voice Agent Call Recordings & Verification

This directory contains three reproducible, end-to-end voice call recordings demonstrating all required Question 1 dialogue scenarios.

## Call Summary Table

| Call ID | Scenario Coverage | Final State | Outcome | Audio Size | Turns | Status |
|:---|:---|:---|:---|:---|:---|:---|
| **call_01_cooperative** | Cooperative Customer (Happy Path) | `qualification_done` | Completed (Eligible) | 690,336 B | 15 | VERIFIED |
| **call_02_objection_conflict** | Objection Handling + Conflicting Details | `qualification_done` | Completed (Underwriting Review) | 1,128,384 B | 19 | VERIFIED |
| **call_03_outofscope_escalation** | Out-of-Scope Query + Human Specialist Transfer | `escalation` | Escalated to Specialist | 684,432 B | 13 | VERIFIED |

---

## Detailed Scenario Breakdown

### 1. `call_01_cooperative`
- **Scenarios Covered**: Cooperative customer, standard qualification flow, grounded product information lookup.
- **Narrative**: Customer Maria Santos (age 35) provides demographic and health info willingly, confirms no pre-existing conditions, inquires about the Gold plan benefits and room rent limit ($500/day per KB), and completes qualification.
- **Artifacts**:
  - [`audio.mp3`](./call_01_cooperative/audio.mp3) (Synthesized two-way dialogue)
  - [`transcript.json`](./call_01_cooperative/transcript.json) (Turn-by-turn timestamps & states)
  - [`result.json`](./call_01_cooperative/result.json) (Qualification profile & outcome)

### 2. `call_02_objection_conflict`
- **Scenarios Covered**: Customer objection handling, incomplete/conflicting details detection, clarification state machine.
- **Narrative**: Customer John Martinez (age 42) initially denies pre-existing conditions and raises an objection regarding the 2-year waiting period. The agent answers using grounded KB objection rationale (risk pooling, Day 1 emergency cover, fine-print copay warnings). Later, the customer discloses daily insulin for diabetes. The agent detects the conflict, avoids inventing an eligibility decision, enters `CLARIFICATION`, logs the conflict in `conflicts_detected`, and explains underwriting guidelines. The customer agrees to explore suitable plans and completes qualification flagged for review.
- **Artifacts**:
  - [`audio.mp3`](./call_02_objection_conflict/audio.mp3)
  - [`transcript.json`](./call_02_objection_conflict/transcript.json)
  - [`result.json`](./call_02_objection_conflict/result.json)

### 3. `call_03_outofscope_escalation`
- **Scenarios Covered**: Out-of-scope query safe fallback (anti-hallucination), human assistance request & supervisor escalation protocol.
- **Narrative**: Customer Sarah Jenkins (age 29) asks about pet insurance vaccination schedules for Golden Retrievers. The retrieval service identifies zero relevant policy records; the agent explicitly states that verified information is unavailable rather than fabricating policy facts. The customer then requests immediate transfer to a licensed specialist/supervisor. The agent executes graceful escalation to human specialist.
- **Artifacts**:
  - [`audio.mp3`](./call_03_outofscope_escalation/audio.mp3)
  - [`transcript.json`](./call_03_outofscope_escalation/transcript.json)
  - [`result.json`](./call_03_outofscope_escalation/result.json)

---

## How to Reproduce

To regenerate all 3 recordings and transcripts from scratch:

```powershell
python scripts/generate_q1_recordings.py
```

To run all automated verification tests:

```powershell
python -m pytest tests/test_q1_scenarios.py -v
```
