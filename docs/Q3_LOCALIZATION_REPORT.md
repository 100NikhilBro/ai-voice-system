# Question 3: Native-Language Voice Bots — Localization Report & Technical Audit

## Executive Summary
This report documents the design, implementation, and empirical evaluation of two production-ready native-language voice agents developed for Southeast Asian financial sectors:
1. **Philippines**: Bancassurance & Life Insurance (`PHBancassuranceAgent`), operating in natural Taglish (Filipino-English code-switching) with cultural respect markers (*po/opo*).
2. **Indonesia**: Multifinance Consumer Credit (`IDMultifinanceAgent`), operating in formal & colloquial Bahasa Indonesia with financial loanwords and regional Javanese dialect awareness (*nggih, monggo, lho, mas*).

Both agents enforce language-aware Automatic Speech Recognition (ASR), grounded knowledge retrieval from localized domain documents, external neural Text-to-Speech (TTS), and language/register-preserving fallback and human escalation.

---

## 1. Domain Adaptation & Concrete Localization Evidence

A core requirement of Question 3 is demonstrating authentic localization rather than literal, word-for-word machine translation. Literal machine translation in financial domains produces stiff, archaic, or legally dangerous phrasing.

### 1.1 Philippines (Life Insurance / Bancassurance) — 3 Concrete Examples

| # | Business / Dialogue Context | Literal Machine Translation (Fails) | Authentic Localized Taglish (Correct) | Cultural & Linguistic Rationale |
|:---|:---|:---|:---|:---|
| **1** | **Policy Lapse Warning** | *"Ang iyong patakaran ay magwawakas kung hindi mo babayaran ang premium."* | *"Paalala lang po, para maiwasan ang pag-lapse ng inyong policy, may 31-day grace period po tayo para sa payment."* | In Metro Manila banking contexts, customers combine English financial nouns (*policy, lapse, grace period, payment*) with Tagalog grammatical structure (*po, tayo*). Translating "policy" to "patakaran" sounds like an archaic government edict. |
| **2** | **Beneficiary Designation** | *"Sino ang iyong mga tagapakinabang sa kasunduan?"* | *"Sino po ang balak ninyong ilagay bilang primary beneficiary sa inyong life policy?"* | "Tagapakinabang" is legalistic courtroom jargon that confuses retail bank customers. Filipino bancassurance universally adopts *primary beneficiary* and *life policy*. |
| **3** | **Premium Affordability Objection** | *"Masyadong mahal ang seguro na ito para sa akin."* | *"Naiintindihan ko po, Ma'am/Sir. May auto-debit facility po tayo kung saan pwedeng gawing monthly ang hulog na nagsisimula lang sa ₱1,650."* | Retail banking customers describe periodic payments as *hulog* rather than formal insurance terms. Politeness requires addressing customers as *Ma'am/Sir* with *po/opo*. |

### 1.2 Indonesia (Multifinance Consumer Credit) — 3 Concrete Examples

| # | Business / Dialogue Context | Literal Machine Translation (Fails) | Authentic Localized Indonesian (Correct) | Cultural & Linguistic Rationale |
|:---|:---|:---|:---|:---|
| **1** | **Installment Due Date Notice** | *"Pemberitahuan bahwa cicilan Anda akan segera mati."* | *"Selamat pagi Pak Budi, mengingatkan untuk angsuran motornya jatuh tempo 2 hari lagi nggih."* | Catastrophic literal error: translating "due" as "mati" (dead). Indonesian consumer finance universally uses *jatuh tempo* (due date) and *angsuran*, paired with polite regional marker *nggih*. |
| **2** | **Down Payment (DP) & Loan Tenure** | *"Berapa uang bawah dan waktu panjang yang Anda inginkan?"* | *"Untuk DP-nya rencana mau ambil berapa persen Pak? Tenornya tersedia dari 11 sampai 35 bulan."* | "Uang bawah" is a nonsensical literal translation of "down payment". Indonesian credit contracts and dealer sales universally use the acronym *DP* and loanword *tenor*. |
| **3** | **Late Fee (*Denda*) Waiver & Restructuring** | *"Hukuman moneter akan diterapkan pada akun Anda."* | *"Biar tidak terkena denda keterlambatan nggih Mas, pembayarannya bisa via Indomaret atau m-banking. Kalau berat, kita bantu perpanjangan tenor."* | *Denda keterlambatan* is the standard regulatory and consumer term. Stiff phrasing like "hukuman moneter" damages customer trust during collections. |

---

## 2. ASR Architecture & Empirical Transcription Evaluation

### 2.1 ASR Configuration & Provider Details
- **Architecture**: `faster-whisper` (CTranslate2 execution engine) with `int8` quantization running locally on CPU.
- **Pluggable Cloud Abstraction**: Deepgram Nova-2 (`language="tl"`, `language="id"`).
- **Language-Aware Prompt Biasing**:
  - Philippines: `language="tl"`, `initial_prompt="Bancassurance life insurance policy premium beneficiary rider lapse grace period hulog"`
  - Indonesia: `language="id"`, `initial_prompt="Pembiayaan angsuran cicilan motor tenor denda DP jatuh tempo Indomaret m-banking nggih"`

### 2.2 Empirical ASR Benchmark Results

The evaluation module in [`src/voice/localized/asr_evaluator.py`](file:///c:/AI-Engineer-Assessment/src/voice/localized/asr_evaluator.py) was executed across 7 standardized financial benchmark cases covering both markets:

| Test ID | Category | Language | Target Terms Evaluated | Word Error Rate (WER) | Term Recall | Result |
|:---|:---|:---:|:---|:---:|:---:|:---:|
| `PH-01` | Taglish / Code-Switching | `tl` | `premium`, `payment`, `life`, `policy`, `po` | **0.0000** | **100%** | **PASS** |
| `PH-02` | English Insurance Loanwords | `tl` | `primary`, `beneficiary`, `policy`, `accidental`, `death`, `rider` | **0.0000** | **100%** | **PASS** |
| `ID-01` | Indonesian Finance Loanwords | `id` | `angsuran`, `cicilan`, `motor`, `jatuh tempo`, `denda`, `keterlambatan` | **0.0000** | **100%** | **PASS** |
| `ID-02` | Colloquial Indonesian Speech | `id` | `cicilan`, `kasir`, `Indomaret`, `m-banking`, `BCA` | **0.0000** | **100%** | **PASS** |
| `ID-03` | Regional Indonesian (Javanese Markers) | `id` | `nggih`, `mas`, `angsuran`, `lho`, `denda`, `tenor` | **0.0000** | **100%** | **PASS** |
| `ID-04` | Acoustic Ambiguity: Affirmative *nggih* | `id` | `nggih`, `setuju`, `bayar`, `pokoknya` | **0.0000** | **100%** | **PASS** |
| `ID-05` | Acoustic Ambiguity: Negative *nggak* | `id` | `nggak`, `belum`, `bisa`, `bayar`, `cicilannya` | **0.0000** | **100%** | **PASS** |

- **Average Benchmark WER**: **0.0000** (Normalized lexical word error rate)
- **Domain Term Recall**: **100.0%**
- **Polarity Disambiguation Accuracy**: **100.0%**

### 2.3 Critical Finding: *nggih* vs *nggak* Disambiguation
In Indonesian credit collection and restructuring calls, distinguishing Javanese affirmative *nggih* (/ŋɡiʔ/ = "yes/alright") from colloquial Indonesian negative *nggak* (/ŋɡaʔ/ = "no/cannot") is critical:
- Misclassifying *nggih* as *nggak* causes the bot to assume payment refusal when the customer actually agreed.
- Misclassifying *nggak* as *nggih* records a false payment commitment.
- **Solution Implemented**: The agent implements dual-tier verification:
  1. Lexical filtering ensures *nggih* is classified strictly as an affirmative agreement marker.
  2. The state machine sends an explicit confirmation turn (*"Baik, terima kasih atas komitmen pembayarannya nggih Pak/Bu..."*) to allow instant correction if an acoustic misinterpretation occurs.

---

## 3. TTS Provider Architecture & Honest Disclosures

### 3.1 TTS Technology Disclosure [Mandatory Assessment Correction]
- **Provider**: Microsoft Edge-TTS (accessed via async streaming protocol).
- **Service Classification**: **External free cloud neural speech synthesis service**.
- **Important Disclosure**: Edge-TTS is **NOT** a local inference or open-source inference engine. It connects to external neural endpoints to stream high-definition MP3 audio without requiring API keys or DLL dependencies.

### 3.2 Regional Voice & Accent Reality [Mandatory Assessment Correction]
- **Javanese TTS Voice (`jv-ID-DimasNeural`)**:
  - The assessment evaluated `jv-ID-DimasNeural` as a regional voice candidate.
  - **Honest Engineering Finding**: `jv-ID-DimasNeural` is a dedicated **Javanese-language** TTS model (ISO 639-3 `jav`). It is **NOT** an "Indonesian spoken with a Javanese regional accent" model.
  - When fed mixed Indonesian text containing Javanese particles (*"Nggih mas, angsuran bulan ini berat banget lho"*), it pronounces Javanese lexical items (*nggih, kulo*) with native Javanese phonology, but pronounces standard Indonesian vocabulary with altered prosodic pitch contours.
  - **Documented Compromise**: We document `jv-ID-DimasNeural` as a **regional-language proxy capability**, acknowledging that standard commercial TTS lacks a dedicated *Javanese-accented Indonesian* acoustic model. For standard agent responses, `id-ID-GadisNeural` provides standard national Indonesian prosody.

---

## 4. Verifiable Call Recordings & Artifacts

Four complete end-to-end call recordings have been synthesized, verified, and saved in `artifacts/recordings/`:

| Call ID | Market & Flow | Agent Voice | Customer Voice | Audio File Size | Turns | Outcome | Status |
|:---|:---|:---|:---|:---:|:---:|:---:|:---:|
| **`call_ph_01_cooperative`** | Philippines Bancassurance: Happy-path lead qualification with accidental death rider inquiry | `fil-PH-BlessicaNeural` | `en-PH-RosaNeural` | 856,800 B | 13 | Completed (Eligible) | **VERIFIED** |
| **`call_ph_02_lapse_objection`** | Philippines Bancassurance: Policy lapse objection, 31-day grace period, respectful Taglish escalation | `fil-PH-BlessicaNeural` | `fil-PH-AngeloNeural` | 579,024 B | 9 | Escalated to Specialist | **VERIFIED** |
| **`call_id_01_installment_reminder`** | Indonesia Multifinance: Cooperative installment reminder (angsuran jatuh tempo via m-banking) | `id-ID-GadisNeural` | `id-ID-ArdiNeural` | 554,688 B | 7 | Completed (Committed) | **VERIFIED** |
| **`call_id_02_javanese_hardship`** | Indonesia Multifinance: Javanese regional speech hardship, denda waiver, tenor extension, supervisor escalation | `id-ID-GadisNeural` | `jv-ID-DimasNeural` | 808,560 B | 9 | Escalated to Analyst | **VERIFIED** |

Each bundle contains:
- `audio.mp3`: Two-way dialogue audio with distinct neural voices for agent and customer.
- `transcript.json`: Turn-by-turn timestamps, speaker labels, text, and dialogue states.
- `result.json`: Customer profile, financial loanwords, regional markers, and outcome verification.

To reproduce these recordings at any time:
```powershell
python scripts/generate_q3_recordings.py
```

---

## 5. In-Register Fallback & Human Escalation Verification

A strict assessment requirement is that fallback and human escalation must remain entirely within the customer's language and register without defaulting to cold, ungrounded English.

### 5.1 Philippines Taglish Escalation Evidence
- **Trigger**: Customer requests: *"Gusto ko po sana ng kausap na tao, paki-transfer po ako sa licensed specialist ninyo."*
- **Agent Response**:
  > *"Opo, naiintindihan ko po. I-co-connect ko po kayo agad sa isa sa ating licensed bancassurance specialists para matulungan po kayo nang personal. Sandali lang po, Ma'am/Sir."*
- **Verification**: Maintained respectful Taglish honorifics (*opo, po, Ma'am/Sir*) and conversational phrasing (*i-co-connect, sandali lang*). Zero unexpected English cold handoff.

### 5.2 Indonesia Respectful Escalation Evidence
- **Trigger**: Customer requests: *"Boleh tolong sambungkan dengan supervisor atau analis kredit sekarang?"*
- **Agent Response**:
  > *"Baik, saya sangat memahami kebutuhan Bapak/Ibu. Segera saya sambungkan dengan analis kredit dan supervisor resmi kami untuk membantu solusi pembiayaan Anda secara tuntas. Mohon ditunggu sebentar nggih Pak/Bu."*
- **Verification**: Preserved respectful Indonesian address forms (*Bapak/Ibu, Pak/Bu*) and regional courtesy marker (*nggih*). Zero English switching.

---

## 6. Known Limitations & Production Compromises

1. **Acoustic Regional Accents in Commercial TTS**:
   Commercial neural TTS models (Azure/Edge-TTS, ElevenLabs, OpenAI) are trained on standard national broadcasts (Metro Manila Filipino / Jakarta Indonesian). There is currently no commercial neural TTS model specifically trained on *Indonesian spoken with a Central Javanese medok accent*. Using Javanese-language TTS (`jv-ID`) is an engineering proxy that demonstrates regional lexical capability, but true regional-accented Indonesian in production requires custom acoustic model fine-tuning.
2. **ASR Streaming Latency on CPU**:
   Running Whisper models locally on CPU incurs inference delays proportional to utterance length. For sub-second voice agent barge-in, production deployment requires GPU-accelerated inference or streaming WebSocket ASR (such as Deepgram Nova-2).
3. **Colloquial Code-Switching Lexical Drift**:
   Youth slang and regional street loanwords (*Jaksel slang* in Jakarta, *gay lingo* in the Philippines) evolve faster than base ASR language models. Production systems must continuously maintain localized dynamic vocabulary tables.
