# Voice Agent Call Recordings & Empirical Evidence Repository

This directory contains reproducible, end-to-end voice call recordings and transcripts across Question 1 (Health Insurance Lead Qualification) and Question 3 (Localized Native-Language Financial Bots for the Philippines and Indonesia).

---

## 1. Master Call Summary Table

| Question | Call ID | Market & Flow | Final State | Outcome | Audio Size | Turns | Status |
|:---:|:---|:---|:---|:---|:---:|:---:|:---:|
| **Q1** | **`call_01_cooperative`** | US Health: Cooperative Lead Qualification | `qualification_done` | Completed (Eligible) | 690,336 B | 15 | **VERIFIED** |
| **Q1** | **`call_02_objection_conflict`** | US Health: Objection + Conflicting Details | `qualification_done` | Completed (Review) | 1,128,384 B | 19 | **VERIFIED** |
| **Q1** | **`call_03_outofscope_escalation`** | US Health: Out-of-Scope Fallback + Escalation | `escalation` | Escalated to Specialist | 684,432 B | 13 | **VERIFIED** |
| **Q3** | **`call_ph_01_cooperative`** | PH Bancassurance: Taglish Lead Qualification | `qualification_done` | Completed (Eligible) | 856,800 B | 13 | **VERIFIED** |
| **Q3** | **`call_ph_02_lapse_objection`** | PH Bancassurance: Lapse Objection & Taglish Escalation | `escalation` | Escalated to Specialist | 579,024 B | 9 | **VERIFIED** |
| **Q3** | **`call_id_01_installment_reminder`** | ID Multifinance: Cooperative Angsuran Reminder | `ended` | Completed (Committed) | 554,688 B | 7 | **VERIFIED** |
| **Q3** | **`call_id_02_javanese_hardship`** | ID Multifinance: Regional Speech Restructuring | `escalation` | Escalated to Analyst | 808,560 B | 9 | **VERIFIED** |

---

## 2. Question 1 Calls (HealthShield Health Insurance)

### `call_01_cooperative`
- **Scenarios**: Cooperative customer happy-path qualification, grounded Gold plan limits.
- **Narrative**: Maria Santos (35) provides all details willingly, asks about room rent limit ($500/day per KB), completes qualification.
- **Files**: [`audio.mp3`](./call_01_cooperative/audio.mp3), [`transcript.json`](./call_01_cooperative/transcript.json), [`result.json`](./call_01_cooperative/result.json).

### `call_02_objection_conflict`
- **Scenarios**: Waiting period objection + conflicting disclosure (denies pre-existing, then mentions daily insulin).
- **Narrative**: John Martinez (42) objects to waiting period; agent responds with grounded pooling rationale. John mentions daily insulin; agent detects conflict, sets `CLARIFICATION`, avoids premature eligibility invention, and guides to suitable plans.
- **Files**: [`audio.mp3`](./call_02_objection_conflict/audio.mp3), [`transcript.json`](./call_02_objection_conflict/transcript.json), [`result.json`](./call_02_objection_conflict/result.json).

### `call_03_outofscope_escalation`
- **Scenarios**: Out-of-scope query safe fallback + human supervisor escalation.
- **Narrative**: Sarah Jenkins (29) asks about pet insurance vaccination schedule. Agent states information unavailable (anti-hallucination). Customer demands supervisor; agent executes graceful escalation.
- **Files**: [`audio.mp3`](./call_03_outofscope_escalation/audio.mp3), [`transcript.json`](./call_03_outofscope_escalation/transcript.json), [`result.json`](./call_03_outofscope_escalation/result.json).

---

## 3. Question 3 Calls (Philippines & Indonesia Localized Bots)

### `call_ph_01_cooperative` (Philippines Bancassurance)
- **Scenarios**: Taglish bancassurance lead qualification, respect honorifics (*po/opo*), accidental death rider inquiry.
- **Narrative**: Maria Santos inquires via bank branch referral, names spouse and children as primary beneficiaries, confirms Accidental Death & Dismemberment rider.
- **Files**: [`audio.mp3`](./call_ph_01_cooperative/audio.mp3), [`transcript.json`](./call_ph_01_cooperative/transcript.json), [`result.json`](./call_ph_01_cooperative/result.json).

### `call_ph_02_lapse_objection` (Philippines Bancassurance)
- **Scenarios**: Policy lapse objection, 31-day grace period, respectful Taglish escalation.
- **Narrative**: Juan raises budget fears of policy lapse. Agent explains 31-day grace period and monthly auto-debit. Juan requests human specialist; agent executes in-register Taglish transfer (*"Opo, naiintindihan ko po. I-co-connect ko po kayo..."*).
- **Files**: [`audio.mp3`](./call_ph_02_lapse_objection/audio.mp3), [`transcript.json`](./call_ph_02_lapse_objection/transcript.json), [`result.json`](./call_ph_02_lapse_objection/result.json).

### `call_id_01_installment_reminder` (Indonesia Multifinance)
- **Scenarios**: Cooperative installment reminder (*angsuran jatuh tempo*), m-banking payment confirmation.
- **Narrative**: Budi Santoso receives friendly reminder for motorcycle installment due date, confirms payment via Mobile Banking Virtual Account before the 15th.
- **Files**: [`audio.mp3`](./call_id_01_installment_reminder/audio.mp3), [`transcript.json`](./call_id_01_installment_reminder/transcript.json), [`result.json`](./call_id_01_installment_reminder/result.json).

### `call_id_02_javanese_hardship` (Indonesia Multifinance)
- **Scenarios**: Regional Javanese speech (*nggih, monggo, lho, mas*), hardship objection, denda waiver, tenor extension, supervisor escalation.
- **Narrative**: Mas Joko explains hardship (*usaha sepi*). Agent acknowledges in empathetic regional register, offers 100% late fee waiver on prompt principal payment and up to 12 months tenor extension, then escalates to credit analyst.
- **Files**: [`audio.mp3`](./call_id_02_javanese_hardship/audio.mp3), [`transcript.json`](./call_id_02_javanese_hardship/transcript.json), [`result.json`](./call_id_02_javanese_hardship/result.json).

---

## 4. How to Reproduce All Recordings

Regenerate all Question 1 call recordings:
```powershell
python scripts/generate_q1_recordings.py
```

Regenerate all Question 3 regional call recordings:
```powershell
python scripts/generate_q3_recordings.py
```

Run complete verification test suite:
```powershell
python -m pytest -v
```
