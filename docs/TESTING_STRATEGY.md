# Comprehensive Testing & Evaluation Strategy

## 1. Overview & Testing Philosophy

This document defines the verification strategy designed to satisfy every evaluation criterion and avoid all rejection conditions outlined in the assessment.

All procedures, benchmarks, and acceptance criteria are categorized into:
- **[Assessment Requirement]**: Strict requirement mandated by the evaluation PDF.
- **[Engineering Decision]**: Test harness architecture, threshold selection, and synthetic test suites created to guarantee repeatability.
- **[Engineering Assumption / Test Placeholder]**: Sample data, illustrative scripts, or configuration defaults used to validate pipeline mechanics. Not treated as real-world policy facts.
- **[Optional Enhancement]**: Supplementary capabilities.

---

## 2. Question 1: Health-Insurance Voice Agent Test Plan

### 2.1 Scenario Coverage Mapping [Assessment Requirement]
The assessment requires at least 3 recorded test calls that collectively cover all 5 required conversation scenarios:
1. **Cooperative customer**
2. **Objection**
3. **Incomplete or conflicting details**
4. **Out-of-scope question**
5. **Human-assistance request**

> **Important Note on Grounding & Test Placeholders**:
> All plan names, waiting periods, and underwriting rules mentioned in test scripts are **synthetic test placeholders** grounded solely in sample source documents ingested for testing. The voice bot possesses zero assumed knowledge of external health insurance policies. If a detail is not present in the ingested source data, the bot must state that the information is unavailable.

| Call ID | Primary Scenarios Covered | Test Call Narrative & Flow | Acceptance Criteria |
|:---|:---|:---|:---|
| **CALL-Q1-01** | • Cooperative customer<br/>• Standard qualification flow | Customer is looking for health coverage for a family, provides clear demographic details, passes health criteria, selects sample plan tier from source docs, confirms budget, and agrees to lead submission. | • Smooth state progression<br/>• Needs discovery completed<br/>• Payload dispatched to Mock CRM<br/>• Audio recording & transcript saved |
| **CALL-Q1-02** | • Objection handling<br/>• Incomplete / conflicting details | Customer seeks individual coverage but objects to a waiting period clause found in the sample source docs. Customer initially denies any pre-existing conditions, but later mentions a regular daily prescription (conflicting details). | • Agent dynamically queries Q2 KB tool for objection rationale<br/>• Agent detects medical conflict, clarifies disclosure, and guides customer<br/>• Grounded citation used in response |
| **CALL-Q1-03** | • Out-of-scope question<br/>• Safe fallback (anti-hallucination)<br/>• Human-assistance request | Customer asks whether the policy covers non-human veterinary care or overseas cosmetic surgery (topics absent from the ingested source data). The bot explicitly states the information is unavailable. Customer then demands to speak with a human supervisor. | • Bot explicitly states information is unavailable without inventing policy facts<br/>• Deterministic trigger of human escalation protocol<br/>• Escalation webhook logged |

### 2.2 Detailed Dialogue Scripts & Step-by-Step Verification

#### Call 1: Cooperative Customer (Happy Path Qualification)
- **User Prompt 1**: *"Hi, I'm looking to get a comprehensive health insurance policy for my family."*
- **Agent Expected**: Acknowledges warmly, initiates qualification: asks for ages of family members and residency.
- **User Prompt 2**: *"It's for myself (38), my spouse (35), and our two kids. None of us have major chronic illnesses."*
- **Agent Expected**: Captures demographic and medical profile, queries KB for family plan options present in source docs, explains coverage features.
- **User Prompt 3**: *"That looks good to me. My budget is around $200 a month."*
- **Agent Expected**: Confirms alignment, captures contact information, triggers `mock_crm_lead_submission`.

#### Call 2: Objection Handling & Conflicting Details
- **User Prompt 1**: *"I want to sign up, but I heard your pre-existing waiting period is 2 years. Why do I have to wait that long before I can make a claim?"*
- **Agent Expected**: Executes `search_health_policy_kb(query="waiting period rationale pre-existing conditions")`. Explains grounded rationale from source documents and highlights immediate emergency coverage.
- **User Prompt 2**: *"Okay fine. I don't have any medical issues anyway."*
- **Agent Expected**: Logs initial negative disclosure. Continues qualification: *"Understood. Have you had any regular prescriptions or consultations in the past 12 months?"*
- **User Prompt 3**: *"Well, just my daily insulin for diabetes, that doesn't count right?"*
- **Agent Expected**: **Detects conflict**. Courteously clarifies: *"Actually, daily insulin indicates a pre-existing condition under our underwriting guidelines. Let me record that accurately so we can guide you to the right plan without claim issues later."*

#### Call 3: Out-of-Scope Fallback & Supervisor Escalation
- **User Prompt 1**: *"Does your policy cover veterinary surgery for my pet and overseas cosmetic procedures in Switzerland?"*
- **Agent Expected**: Executes `search_health_policy_kb(query="veterinary pet care and overseas cosmetic surgery")`.
- **Retrieval Result**: No relevant records in source docs (confidence below threshold).
- **Agent Safe Fallback [Assessment Requirement]**:
  > *"I don't have that information available in my verified policy records. Rather than giving you an inaccurate answer, I will have one of our health insurance specialists follow up with you directly."*
- **User Prompt 2**: *"No, I want to talk to your human supervisor right now. Please transfer me."*
- **Agent Expected**: Triggers `escalate_to_human(reason="customer_requested_supervisor", context="unsupported_policy_query")`. Delivers polite handover statement and terminates voice session cleanly.

---

## 3. Question 2: Health-Insurance Knowledge Base Retrieval Test Plan

### 3.1 Five Mandatory Benchmark Queries [Assessment Requirement]
The assessment requires evaluating at least five specific queries representing five distinct operational categories. All queries are evaluated against sample source documents ingested for testing.

| Query ID | Category | User Query | Expected Retrieved Record & Source | Expected Grounded Rationale |
|:---|:---|:---|:---|:---|
| **KB-TEST-01** | **Product** | *"What are the hospital room rent limits across the plan tiers?"* | `kb_health_sample_004`<br/>*Source: sample_health_benefits_guide.pdf* | Retrieves room rent terms strictly as defined in the ingested sample source document. |
| **KB-TEST-02** | **Policy** | *"What is the waiting period for pre-existing conditions before claims are honored?"* | `kb_health_sample_014`<br/>*Source: sample_underwriting_guide.pdf* | Retrieves pre-existing condition waiting period terms directly from source text. |
| **KB-TEST-03** | **Qualification** | *"What are the maximum age limits and joint surgery disclosure requirements for applicants?"* | `kb_health_sample_021`<br/>*Source: sample_underwriting_sop.html* | Retrieves age qualification boundaries and specific surgical disclosure rules from source. |
| **KB-TEST-04** | **FAQ** | *"How does the cashless hospitalization admission process work at network hospitals?"* | `kb_health_sample_033`<br/>*Source: sample_claim_faq.pdf* | Retrieves step-by-step pre-authorization timelines from source FAQ. |
| **KB-TEST-05** | **Objection** | *"Why is there a premium loading applied for declared tobacco usage?"* | `kb_health_sample_042`<br/>*Source: sample_rating_rules.pdf* | Retrieves actuarial underwriting rationale for tobacco risk loading. |
| **KB-TEST-06** | **Unavailable Fallback Test** | *"Does the policy cover experimental space tourism medical emergencies?"* | `None` (Score $< 0.65$) | System returns explicit fallback: Information unavailable in source documents. Zero hallucination. |

### 3.2 Evaluation Reporting Template [Assessment Requirement]
```
================================================================================
RETRIEVAL TEST RESULT: KB-TEST-02
================================================================================
User Question:       What is the waiting period for pre-existing conditions?
Retrieved Record:    kb_health_sample_014 ("Sample Waiting Period Guidelines")
Source Reference:    sample_underwriting_guide.pdf#p12
Relevance Score:     0.884 (BM25: 14.2, Dense Cosine: 0.82)
PII Flag:            has_pii=False (PII masked: True)
Relevance Reason:    Directly answers query specifying waiting periods for declared
                     conditions based on source document section 3.2.
Verdict:             CORRECT
================================================================================
```

---

## 4. Question 3: Localized Regional Voice Bots Test Plan

### 4.1 Philippines Prototype: Life Insurance / Bancassurance
- **Linguistic Focus**: Natural **Taglish** (Filipino + English code-switching) with cultural respect markers (*po/opo*).
- **Test Calls Required [Assessment Requirement]**:
  1. **CALL-PH-01 (Cooperative Bancassurance Lead)**:
     - Bank customer agrees to discuss life coverage following a branch banking referral.
     - Natural code-switching: captures *premium*, *policy*, and *beneficiary* in authentic Taglish.
  2. **CALL-PH-02 (Objection & Lapse Inquiry)**:
     - Customer raises objection regarding policy *lapse* risks.
     - Bot explains grace period options in polite Taglish without defaulting to English.

#### Adaptation Evidence: Localization vs. Literal Translation (3 Mandatory Examples)
| Domain Context | Literal Machine Translation (Fails) | Authentic Localized Taglish (Correct) | Cultural & Linguistic Rationale |
|:---|:---|:---|:---|
| **1. Policy Lapse Warning** | *"Ang iyong patakaran ay magwawakas kung hindi mo babayaran ang premium."* (Archaic, unnatural). | *"Paalala lang po, para maiwasan ang pag-lapse ng inyong policy, may grace period po tayo para sa payment."* | Filipinos in financial settings integrate loanwords (*policy, lapse, grace period*) into polite Tagalog structure (*po, tayo*). |
| **2. Beneficiary Designation** | *"Sino ang iyong mga tagapakinabang sa kasunduan?"* (Stilted court language). | *"Sino po ang gusto ninyong ilagay bilang primary beneficiary sa inyong policy?"* | Natural financial Taglish uses *primary beneficiary* and *policy*. |
| **3. Objection on Affordability** | *"Masyadong mahal ang seguro na ito para sa akin."* | *"Naiintindihan ko po, Ma'am/Sir. May flexible options po tayo kung saan pwedeng monthly ang hulog."* | Conversational finance uses *hulog* for installments and addresses customers with *Ma'am/Sir* and *po*. |

---

### 4.2 Indonesia Prototype: Multifinance / Consumer Credit
- **Linguistic Focus**: Formal & Colloquial **Bahasa Indonesia** with finance loanwords + **Regional Accent Testing**.
- **Test Calls Required [Assessment Requirement]**:
  1. **CALL-ID-01 (Cooperative Installment Reminder)**:
     - Polite notification regarding an upcoming motorcycle financing *angsuran* due date (*jatuh tempo*).
     - Customer confirms payment schedule via mobile banking.
  2. **CALL-ID-02 (Overdue Restructuring with Regional Accent)**:
     - Customer speaks with a regional accent (e.g., Javanese-Indonesian with dialect markers *monggo, nggih, lho, mas*), explaining payment difficulties.
     - Bot handles objection politely (*Pak/Bu*) and explains *tenor* extension and *denda* waiver procedures.

#### Adaptation Evidence: Localization vs. Literal Translation (3 Mandatory Examples)
| Domain Context | Literal Machine Translation (Fails) | Authentic Localized Indonesian (Correct) | Cultural & Linguistic Rationale |
|:---|:---|:---|:---|
| **1. Installment Due Notice** | *"Pemberitahuan bahwa cicilan Anda akan segera mati."* (Fatal literal error: translates "due" to "mati/dead"). | *"Selamat pagi Pak Budi, mengingatkan untuk angsuran motornya jatuh tempo 2 hari lagi nggih."* | Multifinance uses *jatuh tempo* (due date) and *angsuran/cicilan*, paired with polite regional marker *nggih*. |
| **2. Down Payment & Tenure** | *"Berapa uang bawah dan waktu panjang yang Anda inginkan?"* (Nonsensical literal translation of "down payment" and "tenor"). | *"Untuk DP-nya rencana mau ambil berapa persen Pak? Tenornya tersedia dari 12 sampai 36 bulan."* | Standard Indonesian consumer credit universally uses *DP* and *tenor*. |
| **3. Late Fee Explanation** | *"Hukuman moneter akan diterapkan pada akun Anda."* (Stiff, intimidating language). | *"Biar tidak terkena denda keterlambatan, pembayarannya bisa lewat Indomaret atau transfer m-banking nggih Pak."* | *Denda keterlambatan* is the proper financial term; delivered with helpful payment advice. |

#### Planned Regional Accent Performance & Documented Compromises [Assessment Requirement & Guidance Point 5]
- **Planned ASR Regional Accent Evaluation**:
  - We will evaluate Indonesian ASR (evaluating Deepgram candidates Nova-3 and Flux, with Nova-2 as fallback) against spoken test audio containing non-standard Jakarta regional accent phonology and lexical markers.
  - Planned measurements: We will measure and report word error rates, code-switching behavior, and observed transcription error patterns during test execution.
- **TTS Compromise Documentation (Planned Assessment Evidence)**:
  - We plan to test native Indonesian neural voices (`id-ID-GadisNeural` / `id-ID-ArdiNeural`) for synthesis via the TTS provider abstraction.
  - Known/Expected Limitation: While standard neural TTS models pronounce regional lexical vocabulary accurately, they produce standard national Indonesian prosody rather than authentic regional phonetic dialects.
  - In accordance with PDF Page 3 (*"Native TTS: use Filipino and Indonesian voices where possible; document compromises"*), this phonetic limitation will be documented as an engineering compromise and native-speaker gap.

---

## 5. Question 4: In-Flight Real-Time Nudge Engine Test Plan

### 5.1 Test Coverage Across 4 Mandatory Scenarios [Assessment Requirement]
| Test ID | Audio Input Narrative | Signal Detected | Expected Nudge Output | Verification Criteria |
|:---|:---|:---|:---|:---|
| **Q4-TEST-01** | Customer says: *"It's just for me right now, but my spouse and child might need coverage later this year."* | `SIGNAL_MISSED_CROSS_SELL`<br/>(Confidence: 0.92) | **"💡 Cross-sell Opportunity: Suggest multi-member family coverage discount."** | • Nudge emitted within target latency<br/>• Priority P4 assigned |
| **Q4-TEST-02** | Agent attempts to collect payment details without reading the mandatory waiting-period disclosure. | `SIGNAL_COMPLIANCE_GAP`<br/>(Confidence: 0.96) | **"⚠️ COMPLIANCE GAP: Mandatory pre-existing condition disclosure must be read before proceeding."** | • Immediate P1 alert<br/>• Overrides other notifications |
| **Q4-TEST-03** | Customer tone turns sharp: *"I've repeated my information twice now, are you even listening to me?!"* | `SIGNAL_RISING_FRUSTRATION`<br/>(Confidence: 0.89) | **"🤝 Empathy Alert: Customer is frustrated. Acknowledge the concern before continuing."** | • Emitted within target latency<br/>• Priority P2 assigned |
| **Q4-TEST-04** | Call audio has high background traffic noise, throat clearing, and ambiguous phrases. | None (Confidence scores remain $< 0.50$) | **No nudge emitted** | • Zero spam alerts<br/>• Cooldown and threshold suppress false positives |

### 5.2 Latency Benchmark Harness ($P_{50} / P_{95}$) [Assessment Requirement & Guidance Point 4]
The latency test harness logs timestamps in milliseconds across 5 milestones:
- Audio Received ($T_0$)
- ASR Result ($T_1$)
- Signal Detected ($T_2$)
- Nudge Generated ($T_3$)
- Nudge Delivered ($T_4$)

Empirical metrics reported:
- Component Latencies: ASR ($T_1 - T_0$), Signal Extraction ($T_2 - T_1$), LLM Generation ($T_3 - T_2$), Delivery ($T_4 - T_3$).
- Total End-to-End Latency: $T_4 - T_0$.
- Percentiles: Median ($P_{50}$) and 95th Percentile ($P_{95}$).
- Engineering Performance Goals: $P_{50} \le 2.5\text{s}$, $P_{95} \le 4.5\text{s}$ (meeting assessment requirement of *"useful nudges within seconds"*).

### 5.3 False-Positive Analysis Methodology [Assessment Requirement]
We execute a confusion matrix evaluation against an annotated dataset of conversational audio segments:
- **True Positives (TP)**: Legitimate compliance breach or cross-sell opportunity correctly flagged.
- **False Positives (FP)**: Unnecessary alert triggered during normal conversation or noise.
- **True Negatives (TN)**: Background chatter correctly ignored.
- **False Negatives (FN)**: Genuine compliance breach missed.

$$\text{Precision} = \frac{\text{TP}}{\text{TP} + \text{FP}} \quad (\text{Target} \ge 85\%)$$
$$\text{Recall} = \frac{\text{TP}}{\text{TP} + \text{FN}} \quad (\text{Target} \ge 90\%)$$
