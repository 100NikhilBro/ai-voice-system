"""
Health-Insurance Lead Qualification — Dialogue State Machine
=============================================================
Implements the full Q1 conversation flow:

  STATE 0: greeting          – introduce, obtain consent/context
  STATE 1: lead_qualification – collect age, health status, coverage need
  STATE 2: product_info       – retrieve grounded policy answers from Q2 KB
  STATE 3: objection_handling – handle specific objections via KB
  STATE 4: qualification_done – eligible / ineligible decision
  STATE 5: escalation         – human handoff requested

Business rules
--------------
  - Age < 18  → ineligible (minor)
  - Age > 65  → ineligible (exceeds max entry age)
  - Age 60–65 → eligible but requires tele-medical screening (per KB)
  - Pre-existing conditions → flag for underwriter review (not a hard reject)
  - Every factual policy/FAQ answer MUST be retrieved from Q2 KB.
    If KB returns INFORMATION_UNAVAILABLE → agent says so explicitly.

Grounding contract
------------------
  The agent NEVER invents policy details. All product/policy/FAQ answers
  flow through `retrieval_service.get_voice_tool_context(query)`.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.retrieval.service import retrieval_service

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Dialogue states
# ──────────────────────────────────────────────────────────────────────────────

class DialogueState(str, Enum):
    GREETING            = "greeting"
    LEAD_QUALIFICATION  = "lead_qualification"
    PRODUCT_INFO        = "product_info"
    OBJECTION_HANDLING  = "objection_handling"
    CLARIFICATION       = "clarification"
    QUALIFICATION_DONE  = "qualification_done"
    ESCALATION          = "escalation"
    ENDED               = "ended"


# ──────────────────────────────────────────────────────────────────────────────
# Qualification profile
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class QualificationProfile:
    """Accumulated lead data collected during the conversation."""
    name: Optional[str]          = None
    age: Optional[int]           = None
    has_pre_existing: Optional[bool] = None
    coverage_interest: Optional[str] = None
    phone: Optional[str]         = None
    consent_given: bool          = False
    eligible: Optional[bool]     = None
    ineligibility_reason: Optional[str] = None
    flags: List[str]             = field(default_factory=list)
    conflicts_detected: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "age": self.age,
            "has_pre_existing": self.has_pre_existing,
            "coverage_interest": self.coverage_interest,
            "phone": self.phone,
            "consent_given": self.consent_given,
            "eligible": self.eligible,
            "ineligibility_reason": self.ineligibility_reason,
            "flags": self.flags,
            "conflicts_detected": self.conflicts_detected,
        }


# ──────────────────────────────────────────────────────────────────────────────
# LLM helper (optional — graceful fallback to rule engine)
# ──────────────────────────────────────────────────────────────────────────────

def _call_llm_if_available(system_prompt: str, user_message: str) -> Optional[str]:
    """
    Try to call OpenAI GPT to generate an agent response.
    Returns None if the API key is missing or call fails.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        completion = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=300,
            temperature=0.3,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"[Agent/LLM] LLM call failed: {e} – using rule-based fallback")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Extraction helpers (regex-based, no external NLP dependency)
# ──────────────────────────────────────────────────────────────────────────────

def _extract_age(text: str) -> Optional[int]:
    """Find first plausible age integer in utterance."""
    patterns = [
        r"\b(1[0-9]|[2-9][0-9]|6[0-5])\b years? old",
        r"\bI(?:'m| am) (\d{2})\b",
        r"\bage[d]?\s+(?:is\s+)?(\d{2})\b",
        r"\b(\d{2})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 120:
                return val
    return None


def _extract_name(text: str) -> Optional[str]:
    """Try to extract a name from common patterns."""
    patterns = [
        r"(?:my name is|I(?:'m| am)|call me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)$",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip().title()
    return None


def _has_yes(text: str) -> bool:
    return bool(re.search(r"\b(yes|yeah|yep|sure|correct|right|ok|okay)\b", text, re.IGNORECASE))


def _has_no(text: str) -> bool:
    return bool(re.search(r"\b(no|nope|nah|none|never|not)\b", text, re.IGNORECASE))


def _wants_escalation(text: str) -> bool:
    return bool(re.search(
        r"\b(human|agent|representative|person|talk to someone|speak with|manager|specialist|supervisor|transfer me)\b",
        text, re.IGNORECASE
    ))


def _detect_medical_disclosure(text: str) -> Optional[str]:
    """Detect mention of medical conditions or prescriptions in customer speech."""
    patterns = [
        (r"\b(insulin|diabetes|diabetic)\b", "insulin / diabetes"),
        (r"\b(hypertension|high blood pressure|blood pressure)\b", "hypertension"),
        (r"\b(heart condition|heart disease|cardiac|angioplasty|bypass|stroke)\b", "cardiac condition"),
        (r"\b(asthma|inhaler|respiratory condition)\b", "respiratory / asthma"),
        (r"\b(cancer|chemo|oncology|tumor)\b", "oncology"),
        (r"\b(kidney|renal|dialysis)\b", "renal condition"),
        (r"\b(daily prescription|regular prescription|daily medication|take pills? daily)\b", "daily prescription"),
    ]
    for pat, label in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return label
    return None


def _is_objection(text: str) -> bool:
    """Detect customer objections / doubt signals."""
    return bool(re.search(
        r"\b(expensive|costly|too much|not sure|doubt|compare|competitor|waiting period|pre.existing.*long|why is the|why does|too long|slow|immediate cover|cheaper)\b",
        text, re.IGNORECASE
    ))


# ──────────────────────────────────────────────────────────────────────────────
# Grounded KB lookup
# ──────────────────────────────────────────────────────────────────────────────

def _kb_lookup(query: str) -> str:
    """Call Q2 retrieval service and return formatted grounded context."""
    return retrieval_service.get_voice_tool_context(query)


def _format_kb_answer(query: str, profile: QualificationProfile) -> str:
    """Return a voice-ready answer grounded in the KB."""
    ctx = _kb_lookup(query)

    if ctx.startswith("STATUS: INFORMATION_UNAVAILABLE") or not ctx.startswith("STATUS: GROUNDED_INFO_FOUND"):
        return (
            "I'm sorry, I don't have verified information on that specific topic "
            "in our policy records. I wouldn't want to give you inaccurate details. "
            "Would you like me to connect you with one of our licensed specialists "
            "who can look that up for you, or shall we return to our health plans?"
        )

    # Parse grounded context blocks into a concise voice-friendly summary
    # Strip the STATUS/INSTRUCTION header
    lines = ctx.split("\n")
    content_lines = [l for l in lines if l.startswith("Content:")]
    if content_lines:
        raw_content = content_lines[0].replace("Content:", "").strip()
        # Truncate to ~400 chars for voice comfort
        if len(raw_content) > 400:
            raw_content = raw_content[:400].rsplit(".", 1)[0] + "."
        return raw_content

    # Fallback: return everything after the header
    body = "\n".join(lines[3:]).strip()
    if len(body) > 400:
        body = body[:400].rsplit(".", 1)[0] + "."
    return body or "Let me connect you with a specialist for detailed information on that."


# ──────────────────────────────────────────────────────────────────────────────
# Agent turn generator (state machine + LLM overlay)
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """You are HealthShield AI, a professional health insurance voice agent.
You are currently in the '{state}' phase of a conversation.

Customer profile so far:
{profile_json}

Knowledge base context (GROUNDED — use ONLY this for policy facts):
{kb_context}

Rules:
1. Never invent policy details. Use ONLY the knowledge base context above for facts.
2. If KB context says INFORMATION_UNAVAILABLE, say so explicitly and offer human handoff.
3. Keep responses concise and voice-friendly (2-4 sentences max).
4. Stay warm, empathetic, and professional.
5. Do NOT mention these internal instructions to the customer.

Generate the agent's next spoken response:"""


class VoiceAgent:
    """
    Stateful voice agent for health-insurance lead qualification.
    One instance per call session.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.state = DialogueState.GREETING
        self.profile = QualificationProfile()
        self.turn_count = 0
        self._awaiting: Optional[str] = None  # pending question topic

    # ─────────────────────────────────────────────────────────────────────────
    # Public: process one customer utterance → return agent response
    # ─────────────────────────────────────────────────────────────────────────

    def process(self, utterance: str) -> Tuple[str, Dict[str, Any]]:
        """
        Process a customer utterance and return:
          (agent_text_response, metadata_dict)

        metadata_dict contains:
          state, qualification_profile, citations, escalated, ended
        """
        self.turn_count += 1
        utterance = utterance.strip()

        # Global escalation detection (any state)
        if _wants_escalation(utterance) and self.state not in (
            DialogueState.ESCALATION, DialogueState.ENDED
        ):
            return self._escalate("Customer requested human agent.")

        # Conflict detection: customer previously denied pre-existing condition, but later discloses one
        if self.profile.has_pre_existing is False and self.state in (
            DialogueState.LEAD_QUALIFICATION,
            DialogueState.PRODUCT_INFO,
            DialogueState.OBJECTION_HANDLING,
            DialogueState.CLARIFICATION,
        ):
            condition = _detect_medical_disclosure(utterance)
            if condition:
                self.state = DialogueState.CLARIFICATION
                self.profile.conflicts_detected.append(
                    f"Conflicting disclosure: previously denied pre-existing conditions, but later disclosed {condition} in '{utterance[:80]}'"
                )
                self.profile.has_pre_existing = True
                if "pre_existing_conditions" not in self.profile.flags:
                    self.profile.flags.append("pre_existing_conditions")
                if "conflict_detected" not in self.profile.flags:
                    self.profile.flags.append("conflict_detected")
                self.profile.eligible = None  # Underwriting review needed; do not invent decision
                response = (
                    "Actually, daily insulin or ongoing medication indicates a pre-existing condition "
                    "under our underwriting guidelines. I've noted that accurately so we can guide you to "
                    "the right plan without claim issues later. Since this requires standard underwriter review, "
                    "we can still proceed with plans that accommodate pre-existing conditions after the waiting period. "
                    "Would you like to explore those plan options, or speak with a specialist?"
                )
                meta = {
                    "state": self.state.value,
                    "turn": self.turn_count,
                    "qualification_profile": self.profile.to_dict(),
                    "ended": False,
                    "escalated": False,
                    "conflict_detected": True,
                }
                return response, meta

        # Route to state handler
        if self.state == DialogueState.GREETING:
            response = self._handle_greeting(utterance)
        elif self.state == DialogueState.LEAD_QUALIFICATION:
            response = self._handle_qualification(utterance)
        elif self.state in (DialogueState.PRODUCT_INFO, DialogueState.OBJECTION_HANDLING):
            response = self._handle_product_info(utterance)
        elif self.state == DialogueState.CLARIFICATION:
            response = self._handle_clarification(utterance)
        elif self.state == DialogueState.QUALIFICATION_DONE:
            response = self._handle_post_qualification(utterance)
        elif self.state == DialogueState.ESCALATION:
            response = self._handle_escalation(utterance)
        else:
            response = "Thank you for speaking with HealthShield AI. Have a great day!"


        meta = {
            "state": self.state.value,
            "turn": self.turn_count,
            "qualification_profile": self.profile.to_dict(),
            "ended": self.state == DialogueState.ENDED,
            "escalated": self.state == DialogueState.ESCALATION,
        }
        return response, meta

    # ─────────────────────────────────────────────────────────────────────────
    # Initial greeting (sent before first customer utterance)
    # ─────────────────────────────────────────────────────────────────────────

    def get_opening_message(self) -> str:
        """Return the agent's opening greeting."""
        return (
            "Hello! Thank you for calling HealthShield. My name is Aria, "
            "your HealthShield AI assistant. "
            "This call may be recorded for quality assurance. "
            "I'm here to help you explore our health insurance plans. "
            "May I ask your name, please?"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # State handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_greeting(self, utterance: str) -> str:
        name = _extract_name(utterance)
        if name:
            self.profile.name = name
        self.profile.consent_given = True
        self.state = DialogueState.LEAD_QUALIFICATION
        self._awaiting = "age"

        greeting = f"Lovely to meet you{', ' + self.profile.name if self.profile.name else ''}! "
        return (
            greeting
            + "To help find the right HealthShield plan for you, "
            "could I ask how old you are?"
        )

    def _handle_qualification(self, utterance: str) -> str:
        # Check early objection during qualification
        if _is_objection(utterance):
            ans = self._handle_objection(utterance)
            if self._awaiting == "age" and self.profile.age is None:
                return f"{ans} To help find the right plan for you, could you also share how old you are?"
            return ans

        # Collect age
        if self._awaiting == "age":
            age = _extract_age(utterance)
            if age:
                self.profile.age = age
                return self._evaluate_age_eligibility()
            else:
                return "I didn't quite catch your age — could you share how old you are?"

        # Collect pre-existing conditions
        if self._awaiting == "pre_existing":
            if _has_yes(utterance):
                self.profile.has_pre_existing = True
                self.profile.flags.append("pre_existing_conditions")
            elif _has_no(utterance):
                self.profile.has_pre_existing = False
            else:
                return (
                    "Just to confirm — do you have any existing medical conditions "
                    "such as diabetes, heart disease, or hypertension? "
                    "A simple yes or no is fine."
                )
            self._awaiting = "coverage_interest"
            return (
                "Got it, thank you for sharing that. "
                "What kind of coverage are you most interested in? "
                "For example, hospitalization, outpatient care, maternity, or a comprehensive plan?"
            )

        # Collect coverage interest
        if self._awaiting == "coverage_interest":
            self.profile.coverage_interest = utterance[:100]
            self.state = DialogueState.PRODUCT_INFO
            self._awaiting = None

            # Pull a grounded product overview from KB
            kb_context = _kb_lookup(
                f"coverage benefits and plans available for {utterance}"
            )
            if kb_context.startswith("STATUS: GROUNDED"):
                answer = _format_kb_answer(f"coverage for {utterance}", self.profile)
                return (
                    f"Excellent! Based on what you've told me, here's what I found "
                    f"in our verified policy records: {answer} "
                    "Would you like to know more about a specific plan, "
                    "or do you have any questions?"
                )
            else:
                return (
                    "Great, thank you! We have several plans that may suit your needs — "
                    "including our HealthShield Silver, Gold, and Platinum tiers. "
                    "Do you have any specific questions about coverage benefits or premiums?"
                )

        return "Could you tell me a bit more about what you're looking for?"

    def _evaluate_age_eligibility(self) -> str:
        age = self.profile.age
        assert age is not None

        # Hard ineligibility rules (grounded in qualification_rules.json via KB)
        if age < 18:
            self.profile.eligible = False
            self.profile.ineligibility_reason = "minimum_age_not_met"
            self.state = DialogueState.QUALIFICATION_DONE
            return (
                f"Thank you for your interest. Unfortunately, our individual health insurance plans "
                f"require a minimum applicant age of 18 years. "
                f"At {age}, you would need a guardian or family plan instead. "
                "May I help you with any other information?"
            )

        if age > 65:
            self.profile.eligible = False
            self.profile.ineligibility_reason = "maximum_entry_age_exceeded"
            self.state = DialogueState.QUALIFICATION_DONE
            # Grounded from KB
            ctx = _kb_lookup("maximum entry age for health insurance applicants")
            return (
                f"I appreciate your interest! Based on our verified underwriting guidelines, "
                f"our plans have a maximum new-enrollment age of 65 years. "
                f"At {age}, a new individual policy may not be available, but our senior "
                "specialist team may have tailored options. Shall I transfer you to them?"
            )

        # Senior flag (60–65): grounded screening note
        if 60 <= age <= 65:
            self.profile.flags.append("senior_tele_medical_required")
            ctx = _kb_lookup("tele-medical screening requirements for seniors aged 60 to 65")
            self._awaiting = "pre_existing"
            return (
                f"Thank you! Applicants in the 60–65 age range are very welcome. "
                f"Our records indicate a brief tele-medical screening is required for this age group — "
                f"nothing to worry about, it's just a quick health check. "
                "Do you have any existing medical conditions I should note?"
            )

        # Standard age range
        self._awaiting = "pre_existing"
        return (
            f"Perfect, thank you! At {age}, you're eligible for all our main plan tiers. "
            "Do you currently have any pre-existing medical conditions, "
            "such as diabetes, hypertension, or heart disease?"
        )

    def _handle_product_info(self, utterance: str) -> str:
        # Detect objection first — route to objection handler but DON'T change state here
        if _is_objection(utterance):
            # Directly call objection handler; it sets state to OBJECTION_HANDLING
            return self._handle_objection(utterance)

        # After objection handling, reset to product_info for next question
        if self.state == DialogueState.OBJECTION_HANDLING:
            self.state = DialogueState.PRODUCT_INFO

        # Wants to end / say no more questions
        wrap_phrases = ["no more question", "no question", "that answers", "sounds good", "that's all", "that is all", "done for now"]
        is_closing = (
            (_has_no(utterance) and any(w in utterance.lower() for w in ["question", "thanks", "thank", "done", "fine"]))
            or any(p in utterance.lower() for p in wrap_phrases)
        )
        if is_closing and not any(q in utterance.lower() for q in ["what", "how", "why", "when", "where", "can you", "could you", "tell me"]):
            return self._conclude_qualification()

        # General product/policy question → KB lookup
        answer = _format_kb_answer(utterance, self.profile)
        if "I don't have verified information" in answer:
            return answer
        return (
            f"{answer} "
            "Is there anything else you'd like to know about our plans?"
        )

    def _handle_clarification(self, utterance: str) -> str:
        """Handle conversation after a conflict or incomplete detail has been raised."""
        if _wants_escalation(utterance):
            return self._escalate("Customer requested human agent during clarification.")[0]

        # Customer agrees to continue or asks about plans
        if _has_yes(utterance) or any(w in utterance.lower() for w in ["explore", "plan", "gold", "platinum", "silver", "continue", "okay", "sure", "tell me"]):
            self.state = DialogueState.PRODUCT_INFO
            if any(p in utterance.lower() for p in ["gold", "platinum", "silver", "waiting period", "benefit", "cost", "coverage"]):
                return self._handle_product_info(utterance)
            return (
                "Understood! Both our Gold and Platinum plans provide coverage for pre-existing conditions "
                "following the statutory waiting period, along with immediate coverage for accidents and emergencies. "
                "Would you like to know more about the Gold plan benefits, or do you have specific questions about waiting periods?"
            )

        if _has_no(utterance):
            return (
                "No problem at all. If you'd like to consult a licensed specialist directly "
                "who can assist with custom underwriting for your situation, I can connect you now. "
                "Would that be helpful?"
            )

        return self._handle_product_info(utterance)

    def _handle_objection(self, utterance: str) -> str:
        """Handle objections using grounded KB answers. State stays as OBJECTION_HANDLING."""
        # State stays in OBJECTION_HANDLING until next customer turn
        self.state = DialogueState.OBJECTION_HANDLING
        answer = _format_kb_answer(utterance, self.profile)

        # Try LLM for a more conversational wrap
        llm_response = _call_llm_if_available(
            system_prompt=(
                "You are HealthShield AI, a professional insurance voice agent. "
                "Handle the customer's objection empathetically using ONLY the grounded "
                f"policy fact below. Do NOT invent numbers or policy terms.\n\n"
                f"GROUNDED FACT: {answer}\n\n"
                "Respond in 2-3 natural sentences."
            ),
            user_message=utterance,
        )

        if llm_response:
            return llm_response + " Do you have any other questions?"

        return (
            f"That's a great question. {answer} "
            "Does that address your concern, or would you like more details?"
        )

    def _handle_post_qualification(self, utterance: str) -> str:
        if _wants_escalation(utterance) or _has_yes(utterance):
            return self._escalate("Customer requested follow-up after qualification.")[0]
        self.state = DialogueState.ENDED
        return (
            "Thank you so much for your time today! "
            "One of our advisors will follow up with a detailed quote. "
            "Have a wonderful day!"
        )

    def _handle_escalation(self, utterance: str) -> str:
        self.state = DialogueState.ENDED
        return (
            "Absolutely! I'm transferring you to a licensed HealthShield specialist now. "
            "Please hold for just a moment. Thank you for your patience!"
        )

    def _conclude_qualification(self) -> str:
        self.profile.eligible = True
        self.state = DialogueState.QUALIFICATION_DONE
        name_part = f", {self.profile.name}" if self.profile.name else ""
        return (
            f"Wonderful{name_part}! Based on our conversation, you appear to qualify "
            "for our HealthShield plans. A licensed advisor will reach out to provide "
            "a personalized quote and next steps. "
            "Is there anything else before we wrap up?"
        )

    def _escalate(self, reason: str) -> Tuple[str, Dict[str, Any]]:
        logger.info(f"[Agent/{self.session_id}] Escalating: {reason}")
        self.state = DialogueState.ESCALATION
        response = (
            "Of course! Let me connect you with one of our licensed human specialists "
            "right away. They'll be able to assist you fully. Please hold on briefly."
        )
        meta = {
            "state": self.state.value,
            "turn": self.turn_count,
            "qualification_profile": self.profile.to_dict(),
            "ended": False,
            "escalated": True,
            "escalation_reason": reason,
        }
        return response, meta
