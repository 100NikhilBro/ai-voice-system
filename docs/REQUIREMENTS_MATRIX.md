# Requirements Matrix & 48-Hour Scope Boundary

## 1. Executive Summary & Assessment Alignment

This document formalizes the requirements from the **AI Engineer Assessment** specification, maps them against architectural decisions, and establishes strict scope boundaries for the 48-hour delivery window.

### Classification Taxonomy
To maintain strict adherence to the assessment and prevent conflating assumptions with requirements, every item is categorized as:
- **[Assessment Requirement]**: Explicit mandate stated directly in the evaluation PDF. Must be strictly satisfied to avoid rejection conditions.
- **[Engineering Decision]**: Practical technical choice or architectural pattern made by the engineering team to fulfill assessment requirements within production constraints.
- **[Engineering Assumption / Test Placeholder]**: Operational assumption or synthetic sample data used solely to construct test fixtures and demonstrate pipeline mechanics (e.g., sample plan names or sample waiting periods). Not treated as real-world facts.
- **[Optional Enhancement]**: Supplementary capability mentioned in the assessment as optional (e.g., optional business action) or future production scaling.

---

## 2. 48-Hour Scope Boundary

To ensure complete, functional delivery across all four questions within the 48-hour timeline:

### What We Will Build (Functional, Production-Grounded Core)
1. **Health-Insurance Knowledge Base (Q2)**:
   - Dedicated exclusively to the **Health-Insurance Lead Qualification** domain.
   - Ingestion and parsing pipeline for messy business documents (HTML, tables, FAQs, customer inquiries).
   - Document cleaning, boiler-plate removal, and deduplication.
   - **PII Identification and Protection Strategy**: Detects PII (names, phone numbers, emails, identifiers), masks sensitive data, and tags records with `has_pii` boolean metadata.
   - **PostgreSQL + pgvector** schema matching the PDF requirements (`record_id`, `title`, `content`, `category`, `source`, `version`, `has_pii`, `embedding`, `tsv_content`).
   - Grounded hybrid retrieval (pgvector cosine similarity + PostgreSQL full-text search) with RRF ranking and exact source citations.
   - Grounding guarantee: If information is absent from source documents, the system returns an explicit "information unavailable" fallback response rather than hallucinating.
   - Retrieval test suite covering the 5 required query categories (Product, Policy, Qualification, FAQ, Objection).
2. **Health-Insurance Lead Qualification Voice Agent (Q1)**:
   - Dedicated solely to Health-Insurance Lead Qualification.
   - Built with **LiveKit Agents** on **WebRTC** transport for low-latency conversational audio.
   - Conversational state machine: greeting, qualification logic, dynamic KB retrieval for objections/policies, safe fallback, and human escalation.
   - **Dynamic Grounding**: Tool-calling connection to Q2 KB (`search_health_policy_kb`). Zero hardcoded policies or FAQs in the system prompt.
   - **Safe Fallback & Anti-Hallucination**: Bot explicitly states when information is unavailable in the source data.
   - **Human Escalation**: Clean handover trigger upon customer request or unresolved issues.
   - Web calling interface built in **React + TypeScript** with `@livekit/components-react`.
   - Test harness generating 3 recorded test calls covering all 5 required scenarios with full audio and transcripts.
   - Business action: Mock CRM lead qualification payload dispatch.
3. **Native-Language Regional Prototypes (Q3)**:
   - Kept strictly separate from the Q1/Q2 domain:
     - **Philippines Prototype**: Life Insurance / Bancassurance lead qualification in natural **Taglish** (Filipino + English code-switching) with cultural respect markers (*po/opo*) and sector terms (*premium, policy, beneficiary, rider, lapse, coverage, bank referral*).
     - **Indonesia Prototype**: Multifinance / Consumer Credit installment reminder in **Bahasa Indonesia** (formal & colloquial + English loanwords) with terms (*cicilan, tenor, denda, DP, jatuh tempo, angsuran, pembiayaan*), tested against a regional accent outside Jakarta speech.
   - Streaming ASR via **Deepgram** (evaluating **Nova-3** and **Flux** candidates, with **Nova-2** as verified fallback for `en`, `tl`, `id`) and speech output via a **Pluggable TTS Provider Abstraction**.
   - Documented localization vs. literal translation (3 explicit examples per market).
   - Language-specific ASR evaluation and native TTS configuration, documenting real-world compromises and regional accent observations.
   - 4 recorded test calls (2 per market) with full transcripts.
4. **Real-Time In-Flight Call Audio Nudge Engine (Q4)**:
   - In-flight audio streaming pipeline: Live WebRTC audio stream / 1x paced chunk replayer $\to$ Streaming ASR $\to$ Signal Extractor $\to$ Nudge Controller $\to$ WebSocket Dashboard.
   - Real-time signal detection: Missed cross-sell, compliance gap / skipped disclosure, rising customer frustration, payment difficulty.
   - **Nudge Control Mechanism**: Confidence threshold ($\ge 0.75$), duplicate suppression, category cooldowns, priority ordering, and expiry/repetition rules.
   - **Practical Timestamp Instrumentation**: Logs timestamps at:
     $$\text{Audio Received } (T_0) \to \text{ASR Result } (T_1) \to \text{Signal Detected } (T_2) \to \text{Nudge Generated } (T_3) \to \text{Nudge Delivered } (T_4)$$
     Calculates empirical $P_{50}$ and $P_{95}$ latency distributions across components.
   - Real-time Agent Cockpit UI (**React + TypeScript**) displaying live transcripts, detected signals, latency telemetry, and actionable nudges.
   - Benchmark test suite evaluating all 4 required scenarios (cross-sell, skipped disclosure, frustration, noisy audio suppression).
5. **Final Submission Package**:
   - Clean GitHub repository, README, `.env.example`, architecture diagrams, test results, recordings, transcripts, and video walkthrough outline.

### What We Will Simulate (Pragmatic Mocking for Production Scenarios)
1. **Telephony Carrier (PSTN/SIP Trunking)**: Simulated via LiveKit WebRTC web calling interface. Avoids third-party telephony carrier provisioning delays while exercising production WebRTC media streaming.
2. **Downstream Core CRM & Escalation Desk**: Mock REST endpoints receiving lead capture payloads and logging supervisor escalation handovers.
3. **1x Real-Time Audio Chunk Replayer**: Feeds recorded audio in paced chunks at exact 1x speed to enable reproducible latency benchmarking for Q4.

### What We Will NOT Build (Out of 48-Hour Scope)
1. **Commercial Telephony DID Purchasing**: No paid Twilio/Vonage carrier contracts or country-specific phone number leasing.
2. **Multi-Tenant Enterprise RBAC & Billing**: No enterprise IAM, multi-tenant database partitioning, or payment gateway billing.
3. **Custom Acoustic Model Retraining**: No low-level phoneme model retraining from raw corpus; we utilize production ASR/TTS models and evaluate their capabilities and gaps.

---

## 3. Question-by-Question Requirements Matrix

### Question 1: Health-Insurance Lead Qualification Voice Agent
| ID | Requirement Description | Classification | Implementation / Verification Plan | Source Ref |
|:---|:---|:---|:---|:---|
| **Q1-R1** | Select concrete use case: Health-Insurance Lead Qualification | **[Assessment Requirement]** | Dedicated solely to health-insurance lead qualification. | PDF Page 1 |
| **Q1-R2** | Configure voice platform and add conversational script & business rules | **[Assessment Requirement]** | LiveKit Agents worker orchestrating WebRTC audio, Deepgram ASR, OpenAI LLM, and TTS. | PDF Page 1 |
| **Q1-R3** | Connect Question 2 Knowledge Base via tool-calling; do NOT hardcode FAQs/policies in prompt | **[Assessment Requirement]** | LLM dialogue prompt contains flow structure and tool definition `search_health_policy_kb`. Policies and FAQs fetched dynamically from PostgreSQL + pgvector. | PDF Page 1 |
| **Q1-R4** | Design conversation flow: greeting, qualification logic, objection handling, fallback, escalation | **[Assessment Requirement]** | State machine handling qualification stages, grounded objection handling, fallback, and escalation. | PDF Page 1 |
| **Q1-R5** | Grounded objection handling & safe fallback: state when info is unavailable instead of inventing an answer | **[Assessment Requirement]** | If Q2 retrieval returns no grounded match, bot explicitly states information is unavailable and offers specialist callback. Zero hallucination. | PDF Page 1 |
| **Q1-R6** | Deterministic human escalation path | **[Assessment Requirement]** | Escalation trigger on customer explicit request or unresolved repeated objections; fires mock escalation webhook. | PDF Page 1 |
| **Q1-R7** | Provide a callable number or web calling interface | **[Assessment Requirement]** | React + TypeScript web interface using `@livekit/components-react` with microphone capture and real-time audio playback. | PDF Page 1 |
| **Q1-R8** | Record at least three test calls covering all 5 scenarios | **[Assessment Requirement]** | Test suite executing 3 calls collectively covering: (1) Cooperative, (2) Objection + conflicting details, (3) Out-of-scope question + human escalation. | PDF Page 1 |
| **Q1-R9** | Optional business action: Lead creation / mock CRM summary | **[Optional Enhancement]** | Qualification payload dispatched to mock CRM API endpoint. | PDF Page 1 |
| **Q1-D1** | Single-domain isolation | **[Engineering Decision]** | Keep Q1/Q2 strictly focused on Health Insurance. Do not pollute with Q3 bancassurance/multifinance data. | Guidance Point 1 |
| **Q1-D2** | LiveKit + WebRTC Transport | **[Engineering Decision]** | Full-duplex WebRTC audio streaming for sub-150ms voice transport. | Guidance Point 4 |
| **Q1-A1** | Sample health policy figures as test placeholders | **[Engineering Assumption / Test Placeholder]** | Any specific waiting periods or sample plan names in test fixtures are synthetic test placeholders, strictly grounded in sample source documents. | Guidance Point 2 |

---

### Question 2: Production-Ready Health-Insurance Knowledge Base
| ID | Requirement Description | Classification | Implementation / Verification Plan | Source Ref |
|:---|:---|:---|:---|:---|
| **Q2-R1** | Ingest mixed business content (HTML, policies, tables, duplicated data, PII) | **[Assessment Requirement]** | Ingestion pipeline loading health insurance source documents containing messy formatting, tables, and synthetic PII. | PDF Page 2 |
| **Q2-R2** | Document parsing & cleaning (strip headers, nav text, irrelevant content) | **[Assessment Requirement]** | Parser and boiler-plate stripper normalizing raw text into semantic sections. | PDF Page 2 |
| **Q2-R3** | Deduplication and near-duplicate removal | **[Assessment Requirement]** | MinHash/Jaccard deduplication eliminating redundant marketing blurbs. | PDF Page 2 |
| **Q2-R4** | Standardize headings, dates, terminology, categories | **[Assessment Requirement]** | Schema normalization for insurance terms (deductibles, waiting periods, copays). | PDF Page 2 |
| **Q2-R5** | Identify and protect Personally Identifiable Information (PII) | **[Assessment Requirement]** | PII handling strategy: Regex/NER detection, attribute masking (`[CUSTOMER_NAME]`), and metadata flag `has_pii: bool`. | PDF Page 2, Guidance Point 5 |
| **Q2-R6** | Document schema conforming to PDF specification | **[Assessment Requirement]** | Records strictly adhere to schema: `record_id`, `title`, `content`, `category`, `source`, `version`, `has_pii`. | PDF Page 2 |
| **Q2-R7** | Chunking strategy and metadata indexing | **[Assessment Requirement]** | Semantic chunking with parent document metadata tracking in PostgreSQL. | PDF Page 2 |
| **Q2-R8** | Retrieval & ranking logic with citations | **[Assessment Requirement]** | Hybrid search (PostgreSQL `pgvector` HNSW cosine similarity + full-text search `tsvector`) with RRF ranking and exact citations. | PDF Page 2 |
| **Q2-R9** | Benchmark test suite with at least 5 queries across product, policy, qualification, FAQ, objection | **[Assessment Requirement]** | Automated evaluation script testing 5 required query classes, reporting chunk, source, explanation, and verdict. | PDF Page 2 |
| **Q2-R10** | Live connection between Knowledge Base and Question 1 Voice Bot | **[Assessment Requirement]** | Dynamic tool-calling interface enabling real-time retrieval during voice calls. | PDF Page 2 |
| **Q2-R11** | Unavailable information handling | **[Assessment Requirement]** | If source does not contain an answer, retrieval engine returns an explicit fallback indication rather than generating ungrounded facts. | PDF Page 1, 2 |

---

### Question 3: Native-Language Localized Voice Bots
| ID | Requirement Description | Classification | Implementation / Verification Plan | Source Ref |
|:---|:---|:---|:---|:---|
| **Q3-R1** | Two separate localized prototypes with independent domain content and rules | **[Assessment Requirement]** | Independent configuration files, prompts, and lexicons for Philippines and Indonesia. | PDF Page 3 |
| **Q3-R2** | **Philippines Prototype**: Life Insurance / Bancassurance | **[Assessment Requirement]** | Bancassurance lead qualification / renewal flow supporting English, Tagalog, and authentic Taglish code-switching. | PDF Page 3 |
| **Q3-R3** | Philippines natural terminology & cultural markers | **[Assessment Requirement]** | Incorporate terms (*premium, policy, beneficiary, rider, lapse, coverage, bank referral*) and respect markers (*po, opo*). | PDF Page 3 |
| **Q3-R4** | **Indonesia Prototype**: Multifinance / Consumer Credit | **[Assessment Requirement]** | Multifinance installment reminder flow supporting formal & colloquial Bahasa Indonesia + English loanwords. | PDF Page 3 |
| **Q3-R5** | Indonesia regional accent testing & performance observation | **[Assessment Requirement]** | Test Deepgram Indonesian ASR against at least one regional accent outside Jakarta speech; evaluate transcription performance and document observed errors and gaps. | PDF Page 3, Guidance Point 5 |
| **Q3-R6** | Indonesia natural financial terminology | **[Assessment Requirement]** | Incorporate terms (*cicilan, tenor, denda, DP, jatuh tempo, angsuran, pembiayaan*). | PDF Page 3 |
| **Q3-R7** | Language-specific ASR evaluation | **[Assessment Requirement]** | Configure and test Deepgram candidate models (Nova-3, Flux, Nova-2 fallback) for `fil-PH` and `id-ID`; report code-switching behavior, approximate quality, and errors. | PDF Page 3 |
| **Q3-R8** | Native TTS selection & compromise documentation | **[Assessment Requirement]** | Pluggable TTS abstraction (Edge-TTS / ElevenLabs / OpenAI); document compromises (e.g. standard accent used by TTS vs regional accent inputs). | PDF Page 3 |
| **Q3-R9** | Adaptation evidence: $\ge 3$ localization examples per market | **[Assessment Requirement]** | Report documenting 3 concrete examples per market demonstrating localized phrasing vs literal translation. | PDF Page 3 |
| **Q3-R10** | Fallback/escalation within customer language & register | **[Assessment Requirement]** | Escalation prompts remain in customer's language without unexpected switching to English. | PDF Page 3 |
| **Q3-R11** | Test coverage: 2 recorded calls per market (4 total) | **[Assessment Requirement]** | Execute and record 2 calls for Philippines and 2 calls for Indonesia with full transcripts. | PDF Page 3 |

---

### Question 4: Real-Time In-Flight Call Audio Nudge Engine
| ID | Requirement Description | Classification | Implementation / Verification Plan | Source Ref |
|:---|:---|:---|:---|:---|
| **Q4-R1** | Analyze call **while it is happening** (in-flight before call ends) | **[Assessment Requirement]** | Streaming pipeline analyzing active transcript and audio continuously. Post-call analysis does not qualify. | PDF Page 4 |
| **Q4-R2** | Streaming input: Live audio or 1x real-time chunked replay | **[Assessment Requirement]** | LiveKit WebRTC audio stream / 1x paced chunk replayer feeding Deepgram ASR. | PDF Page 4 |
| **Q4-R3** | Continuous streaming ASR with speaker separation | **[Assessment Requirement]** | Streaming transcription outputting incremental text with agent/customer separation where possible. | PDF Page 4 |
| **Q4-R4** | Signal extraction covering core categories | **[Assessment Requirement]** | Detect: (1) Missed cross-sell, (2) Compliance gap, (3) Rising frustration, (4) Payment difficulty. | PDF Page 4 |
| **Q4-R5** | Timestamp instrumentation ($T_0 \to T_4$) | **[Assessment Requirement]** | Log practical millisecond timestamps for: Audio Received ($T_0$), ASR Result ($T_1$), Signal Detected ($T_2$), Nudge Generated ($T_3$), Nudge Delivered ($T_4$). | PDF Page 4, Guidance Point 4 |
| **Q4-R6** | Latency reporting ($P_{50} / P_{95}$ & component breakdown) | **[Assessment Requirement]** | Measure and report $P_{50}$ and $P_{95}$ empirical latency across ASR, signal extraction, LLM, and delivery. | PDF Page 4 |
| **Q4-R7** | Concrete nudge-control mechanism | **[Assessment Requirement]** | Multi-tier filter: Confidence threshold, duplicate suppression, category cooldown, priority ordering, expiry/repetition rules. | PDF Page 4, Guidance Point 9 |
| **Q4-R8** | Quality & false-positive analysis | **[Assessment Requirement]** | Quantitative evaluation of nudge accuracy, precision, and suppression on noisy/ambiguous calls. | PDF Page 4 |
| **Q4-R9** | Test coverage: 4 distinct call scenarios | **[Assessment Requirement]** | Test suite evaluating: (1) Missed cross-sell, (2) Skipped disclosure, (3) Frustration, (4) Noisy/ambiguous call without unnecessary nudges. | PDF Page 4 |
| **Q4-R10** | Agent Cockpit UI / WebSocket delivery | **[Assessment Requirement]** | React + TypeScript web dashboard presenting live transcript, audio status, signal feed, and prioritized nudges. | PDF Page 4 |
| **Q4-E1** | Realistic engineering latency targets | **[Engineering Decision]** | Engineering performance targets: $P_{50} \le 2.5\text{s}, P_{95} \le 4.5\text{s}$. (Engineering goals, fulfilling assessment requirement of "useful nudges within seconds"). | Guidance Point 4 |
| **Q4-E2** | 10x scale and noisy audio limitation analysis | **[Assessment Requirement]** | Technical evaluation explaining system behavior and bottlenecks at 10x concurrency and under acoustic noise. | PDF Page 4 |
