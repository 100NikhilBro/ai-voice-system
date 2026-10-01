# Technology Stack & Tooling Rationale

## 1. Stack Overview & Selection Principles

This document defines the primary technology stack for the **AI Engineer Assessment**, aligned with modern real-time voice architectures and production constraints.

The stack combines:
- **LiveKit + WebRTC** with **LiveKit Agents** for full-duplex conversational voice.
- **Deepgram Streaming ASR** (evaluating **Nova-3** and **Flux** for real-time multilingual performance, with **Nova-2** as a verified fallback).
- **OpenAI** for grounded dialogue reasoning, structured tool calling, and in-flight signal detection.
- **PostgreSQL + pgvector** for production-grade hybrid retrieval (vector similarity + full-text search).
- **React + TypeScript** for the web calling interface and real-time agent cockpit.
- **Pluggable TTS Provider Abstraction** to evaluate and document compromises across native Filipino and Indonesian voices.

---

## 2. Distinction of Latency & Performance Terms

To ensure clear technical communication, this project strictly differentiates:
1. **Provider-Claimed / Protocol Capabilities**: Theoretical capabilities cited by protocol specifications or vendor documentation (e.g., WebRTC protocol characteristics or vendor API turnarounds). These are **not** our measured results.
2. **Engineering Targets**: Internal performance goals set by our engineering team to ensure the system satisfies assessment goals (e.g., aiming for end-to-end nudge delivery within seconds).
3. **Measured Assessment Results**: Actual empirical metrics measured and recorded by our timestamp instrumentation harness during test runs. *(These will be captured during test execution, not asserted prematurely).*

---

## 3. Primary Technology Matrix

Every technology in the stack is documented below with:
1. **Why we are using it**
2. **Which assessment requirement it supports**
3. **Important limitations, candidate evaluations, and practical fallback**

| Technology | Classification | 1. Why We Are Using It | 2. Assessment Requirement Supported | 3. Limitations, Candidates & Fallbacks |
|:---|:---|:---|:---|:---|
| **Python 3.11+ / FastAPI / asyncio** | **[Engineering Decision]** | Industry-standard async backend; native support for streaming WebSockets, concurrent task loops, and LiveKit Agents worker processes. | Foundation for Q1 Voice Bot, Q2 KB API, and Q4 Nudge Engine. | *Limitation*: CPU-bound audio processing must be async-safe.<br/>*Fallback*: Standard asyncio thread executors. |
| **React + TypeScript** | **[Engineering Decision]** | Type-safe, component-driven UI library with official `@livekit/components-react` support for WebRTC audio tracks, live waveforms, and real-time state. | Q1 Web Calling Interface (PDF p.1) & Q4 Agent Cockpit Dashboard (PDF p.4). | *Limitation*: Requires Vite dev server / build step.<br/>*Fallback*: Standalone Vite single-page application. |
| **LiveKit + WebRTC** | **[Engineering Decision]** | Standard WebRTC media server providing full-duplex bidirectional audio transport, jitter buffering, and clean browser audio track handling. | Q1 Callable web calling interface (PDF p.1); Q4 Streaming audio input (PDF p.4). | *Limitation*: Requires running LiveKit media server (`livekit-server --dev` or LiveKit Cloud).<br/>*Fallback*: Direct WebSocket audio streaming over FastAPI if WebRTC port range is blocked. |
| **LiveKit Agents** | **[Engineering Decision]** | Real-time voice agent framework orchestrating VAD (Voice Activity Detection), barge-in handling, ASR streaming, LLM tool execution, and TTS synthesis into a coherent conversational loop. | Q1 Voice agent conversation flow, grounded qualification, and tool execution (PDF p.1). | *Limitation*: Worker model requires background orchestration process.<br/>*Fallback*: In-process FastAPI async dialogue manager state machine. |
| **Deepgram Streaming ASR** | **[Engineering Decision]** | High-throughput streaming transcription via WebSockets. We plan to evaluate **Nova-3** and **Flux** for multilingual accuracy, keeping **Nova-2** as a stable fallback. | Q1 Voice Agent ASR (p.1); Q3 Language-specific ASR evaluation (p.3); Q4 Continuous streaming ASR (p.4). | *Limitation*: Mixed Taglish code-switching and non-standard regional accents require empirical verification.<br/>*Candidates*: Nova-3 (enhanced multilingual), Flux (streaming-optimized).<br/>*Fallback*: Nova-2 as verified fallback; Faster-Whisper local streaming fallback. |
| **OpenAI (GPT-4o / GPT-4o-mini)** | **[Engineering Decision]** | Deterministic function calling for Q1 dynamic KB lookup; reliable JSON schema adherence for Q4 signal detection; high reasoning speed. | Q1 Dialogue flow & dynamic KB tool-calling (p.1); Q4 In-flight signal & nudge generation (p.4). | *Limitation*: Cloud API rate limits and network latency variance.<br/>*Fallback*: Gemini 1.5 Flash provider fallback. |
| **TTS Provider Abstraction** | **[Engineering Decision]** | Clean interface isolating speech synthesis (`synthesize(text, lang, voice)`), enabling planned evaluation of Edge-TTS, ElevenLabs, and OpenAI TTS. | Q1 Bot voice output (p.1); Q3 Native TTS selection & compromise documentation (p.3). | *Limitation*: Commercial neural TTS models speak standard national accents rather than authentic regional phonetic dialects.<br/>*Fallback*: Standard national voice configured with regional vocabulary, documenting the limitation as required by the assessment. |
| **PostgreSQL + pgvector** | **[Engineering Decision]** | Unified, production-grade relational database with vector search (`HNSW` indexing) and ACID compliance. Preserves schema metadata (`record_id`, `category`, `source`, `version`, `has_pii`). | Q2 Production-Ready Knowledge Base design, schema, and traceable records (PDF p.2). | *Limitation*: Requires PostgreSQL instance with `pgvector` extension.<br/>*Fallback*: Docker container (`pgvector/pgvector:pg16`), with an embedded SQLite FTS5 fallback if local PostgreSQL is inaccessible. |
| **Hybrid Search + Reranking** | **[Engineering Decision]** | Combines vector semantic similarity (pgvector cosine `<=>`) with PostgreSQL Full-Text Search (`tsvector` / `ts_rank_cd`), followed by Reciprocal Rank Fusion (RRF). | Q2 Grounded retrieval, citations, and reliable objection/policy matching (PDF p.2). | *Limitation*: Hybrid ranking requires score normalization.<br/>*Fallback*: Standard RRF ($1 / (k + \text{rank})$) with exact source citations. |
| **Q4 In-Flight Nudge Engine** | **[Assessment Requirement]** | Streaming pipeline: Transcript $\to$ Signal Extractor $\to$ Nudge Controller (cooldown, confidence, deduplication) $\to$ WebSocket to React Cockpit. | Q4 Live insights & nudges from call audio before call ends (PDF p.4). | *Limitation*: Rapid speaker turns can generate redundant signals if unconstrained.<br/>*Fallback*: 5-tier nudge controller strictly enforces cooldown and confidence gating. |

---

## 4. Deepgram Model Candidates & Planned Language Evaluations

Rather than prematurely locking a single ASR model, we define candidate models and a planned evaluation matrix:

### 4.1 ASR Model Candidates for Evaluation
1. **Deepgram Nova-3**: Primary candidate for multilingual accuracy, recent vocabulary improvements, and multi-speaker transcription.
2. **Deepgram Flux / Streaming Variants**: Candidate for optimized streaming turnaround and minimal chunking latency.
3. **Deepgram Nova-2**: Documented, stable fallback option with established production baselines for `en`, `tl`, and `id`.
4. **Faster-Whisper (Local)**: Local offline fallback for comparative benchmarking and offline resilience.

### 4.2 Planned ASR Evaluation Matrix (To Be Empirically Tested)

| Language / Dialect | Planned Test Configurations | Planned Evaluation Focus | Hypothesized Limitation / Risk to Validate | Fallback Option |
|:---|:---|:---|:---|:---|
| **English (Global/Financial)** | Deepgram (Nova-3 / Flux / Nova-2), `language=en` | Financial terminology, policy numbers, and numerical accuracy under streaming chunking. | Potential acronym misinterpretation under low audio bitrates. | Keyword biasing dictionary. |
| **Tagalog / Filipino** | Deepgram `language=tl` | Recognition of formal/conversational Tagalog, honorific markers (*po, opo*). | Standard model sensitivity to English loanwords. | Keyword biasing for common policy terms. |
| **Taglish (Code-Switching)** | Deepgram `language=tl` vs `language=en` | Rapid alternation between English and Tagalog within single conversational turns. | Code-switching language identification lag or transliteration of English terms when set to `tl`. | Comparative benchmark of both language settings; local Whisper multilingual fallback. |
| **Bahasa Indonesia (Standard)** | Deepgram `language=id` | Standard financial loanwords (*cicilan, tenor, denda, DP, jatuh tempo, angsuran*). | Colloquial particle omissions (*lho, kok, kan*). | Financial keyterm dictionary biasing. |
| **Indonesia Regional Accent** | Deepgram `language=id` tested on regional spoken audio | Transcription accuracy on non-standard Jakarta speech (e.g. Javanese-Indonesian regional markers and phonological variations). | **Hypothesized Limitation**: Regional phonological shifts and non-standard lexical items may lead to elevated word error rates (WER) or phonetic substitutions. | **Planned Assessment Action**: Measure and log empirical WER and error patterns during test execution. Fallback to Whisper with regional prompt conditioning. |

---

## 5. TTS Provider Abstraction & Planned Voice Evaluations

The application defines a unified TTS interface:
```python
class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, language: str, voice_id: Optional[str] = None) -> AsyncIterator[bytes]:
        """Stream synthesized audio chunks."""
        pass
```

### Planned Provider Evaluations & Documented Compromises

1. **Edge-TTS (Primary Candidate for Native Voices)**:
   - **Philippines**: Voice candidates `fil-PH-BlessicaNeural` (Female) and `fil-PH-AngeloNeural` (Male).
   - **Indonesia**: Voice candidates `id-ID-GadisNeural` (Female) and `id-ID-ArdiNeural` (Male).
   - **Expected Limitation**: Produces standard national prosody; does not simulate regional phonetic dialects (e.g., Javanese *medok* intonation).
   - **Assessment Compromise**: In accordance with PDF Page 3 (*"Native TTS: use Filipino and Indonesian voices where possible; document compromises"*), this phonetic limitation will be documented as an industry constraint of commercial neural speech synthesis.

2. **OpenAI TTS (Cloud Baseline)**:
   - Voices: `alloy`, `echo`, `shimmer`, `nova`.
   - **Known Limitation**: Non-English texts are pronounced with an international/American phonetic accent, resulting in less authentic prosody for Tagalog and Indonesian.

3. **ElevenLabs (Optional Enhanced Cloud Provider)**:
   - Evaluated for naturalness if API quota is configured.

---

## 6. Knowledge Base: PostgreSQL + pgvector Hybrid Architecture

```mermaid
flowchart TD
    Query["User Query / Voice Tool Call"] --> EmbeddingGen["Generate Query Vector<br/>(text-embedding-3-small)"]
    Query --> QueryTokens["Parse Search Terms<br/>(websearch_to_tsquery)"]

    EmbeddingGen --> VectorSearch["pgvector Semantic Search<br/>(HNSW Cosine Distance <=> )"]
    QueryTokens --> TextSearch["PostgreSQL FTS<br/>(ts_rank_cd on tsvector)"]

    VectorSearch --> RRF["Reciprocal Rank Fusion (RRF)<br/>Score = 1/(k + Rank_vec) + 1/(k + Rank_fts)"]
    TextSearch --> RRF

    RRF --> Threshold{"Relevance Score >= 0.65?"}
    Threshold -- Yes --> TopK["Return Top Ranked Chunks<br/>+ record_id + source citation"]
    Threshold -- No --> Fallback["Return Explicit Fallback:<br/>'Information unavailable in source documents'"]
```

### PostgreSQL Schema
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE health_kb_records (
    record_id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(64) NOT NULL,
    source VARCHAR(255) NOT NULL,
    version VARCHAR(16) NOT NULL DEFAULT '1.0',
    has_pii BOOLEAN NOT NULL DEFAULT FALSE,
    pii_types TEXT[] DEFAULT '{}',
    embedding vector(1536),
    tsv_content tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || content)) STORED,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_kb_vector ON health_kb_records USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_kb_tsv ON health_kb_records USING gin (tsv_content);
CREATE INDEX idx_kb_category ON health_kb_records (category);
```

---

## 7. Q4 Real-Time Nudge Pipeline Architecture

```mermaid
flowchart LR
    DeepgramASR["Streaming ASR<br/>(Nova-3 / Flux / Nova-2)"] -->|Chunk Transcribed| TranscriptStream["Streaming Transcript Buffer<br/>(Agent & Customer Turns)"]
    TranscriptStream -->|Trigger Event| SignalEngine["In-Flight Signal Extractor<br/>(Cross-sell, Compliance, Sentiment)"]
    SignalEngine -->|Candidate Signal| NudgeCtrl["Nudge Controller<br/>(Confidence, Cooldown, Duplicate, TTL)"]
    NudgeCtrl -->|Approved Nudge + T0..T4| WSServer["FastAPI WebSocket Server"]
    WSServer -->|Live JSON Message| ReactUI["React + TypeScript<br/>Agent Cockpit Dashboard"]
```

### Timestamp Telemetry Flow
```
T0: Audio Chunk Received at Server
T1: ASR Result Emitted by Deepgram
T2: Signal Detected by Signal Engine
T3: Nudge Generated by OpenAI LLM
T4: Nudge Delivered to React UI via WebSocket

Metrics To Be Measured During Test Execution:
- ASR Latency: T1 - T0
- Signal Extraction Latency: T2 - T1
- LLM Generation Latency: T3 - T2
- Delivery Latency: T4 - T3
- Total End-to-End Latency: T4 - T0
- Empirical Distribution: Measured P50 and P95 percentiles
- Engineering Targets: P50 <= 2.5s, P95 <= 4.5s
```

---

## 8. Environment Configuration (`.env.example`)

```ini
# ==========================================
# Primary Tech Stack Environment Configuration
# ==========================================

# Application Server
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
REACT_APP_PORT=3000

# LiveKit WebRTC Transport
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
LIVEKIT_AGENT_NAME=health-insurance-agent

# Speech-to-Text (ASR) Candidate Configuration
DEEPGRAM_API_KEY=your_deepgram_api_key_here
DEEPGRAM_MODEL=nova-3 # candidates: nova-3, flux, nova-2 (fallback)
DEEPGRAM_LANGUAGE=en # en, tl, or id

# Language Models (LLM)
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Text-to-Speech (TTS Provider Abstraction)
PRIMARY_TTS_PROVIDER=edge-tts # options: edge-tts, elevenlabs, openai
ELEVENLABS_API_KEY=optional_elevenlabs_key

# Knowledge Base (PostgreSQL + pgvector)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/health_insurance_kb
POSTGRES_DB=health_insurance_kb
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Q4 Real-Time Nudge Controls (Engineering Targets)
NUDGE_CONFIDENCE_THRESHOLD=0.75
NUDGE_COOLDOWN_SECONDS=30
NUDGE_DUPLICATE_SIMILARITY_THRESHOLD=0.80
NUDGE_DEFAULT_TTL_SECONDS=30

# Mock CRM & Escalation Webhooks
MOCK_CRM_ENDPOINT=http://localhost:8000/api/v1/mock/crm/lead
MOCK_ESCALATION_ENDPOINT=http://localhost:8000/api/v1/mock/escalation/agent
```
