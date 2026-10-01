"""
Philippines Bancassurance Life Insurance Voice Agent
====================================================
Implements natural Taglish (Filipino + English code-switching) dialogue
for bancassurance life lead qualification, coverage inquiries, and objection handling.

Cultural and Linguistic Features:
- Respect honorifics: po, opo, ho, Ma'am/Sir
- Authentic Taglish blending Tagalog grammatical syntax with English financial terms:
  premium, policy, beneficiary, rider, lapse, grace period, coverage, bank referral, hulog
- Fallback & escalation strictly preserve the polite Taglish customer register.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PH_DOMAIN_DIR = Path(__file__).resolve().parent.parent.parent.parent / "domains" / "philippines_bancassurance" / "raw_docs"


class PHDialogueState(str, Enum):
    GREETING            = "greeting"
    LEAD_QUALIFICATION  = "lead_qualification"
    PRODUCT_INFO        = "product_info"
    OBJECTION_HANDLING  = "objection_handling"
    CLARIFICATION       = "clarification"
    QUALIFICATION_DONE  = "qualification_done"
    ESCALATION          = "escalation"
    ENDED               = "ended"


@dataclass
class PHLeadProfile:
    name: Optional[str]              = None
    age: Optional[int]               = None
    referral_bank: Optional[str]     = None
    beneficiary_relation: Optional[str] = None
    coverage_interest: Optional[str] = None
    preferred_payment: Optional[str] = None
    eligible: Optional[bool]         = None
    flags: List[str]                 = field(default_factory=list)
    conflicts_detected: List[str]    = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "age": self.age,
            "referral_bank": self.referral_bank,
            "beneficiary_relation": self.beneficiary_relation,
            "coverage_interest": self.coverage_interest,
            "preferred_payment": self.preferred_payment,
            "eligible": self.eligible,
            "flags": self.flags,
            "conflicts_detected": self.conflicts_detected,
        }


def _extract_age(text: str) -> Optional[int]:
    patterns = [
        r"\b(\d{2})\b\s*(?:years? old|anyos|taon)",
        r"(?:ako ay|I'm|I am|edad ko ay)\s*(\d{2})",
        r"\b(\d{2})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 100:
                return val
    return None


def _extract_name(text: str) -> Optional[str]:
    patterns = [
        r"(?:my name is|ako(?:\s+po)?\s+si|pangalan ko(?:\s+po)?\s+ay|I'm|I am|tawagin mo akong)\s+([A-Za-z]+(?:\s+[A-Za-z]+)*)",
        r"^([A-Za-z]+(?:\s+[A-Za-z]+)*)$",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            clean = m.group(1).strip()
            # Stop if punctuation or filler
            clean = re.split(r"[,.!?]", clean)[0].strip()
            if len(clean) >= 2:
                return clean.title()
    return None


def _is_taglish_affirmative(text: str) -> bool:
    return bool(re.search(r"\b(opo|oo|yes|yep|sige|sige po|pwede|pwede po|okay|ok|sure|agree)\b", text, re.IGNORECASE))


def _is_taglish_negative(text: str) -> bool:
    return bool(re.search(r"\b(hindi|hindi po|no|nope|wala|wala po|ayaw|huwag)\b", text, re.IGNORECASE))


def _wants_ph_escalation(text: str) -> bool:
    return bool(re.search(
        r"\b(kausap na tao|human agent|taong kausap|supervisor|specialist|transfer|i-connect|licensed agent|manager)\b",
        text, re.IGNORECASE
    ))


def _is_ph_objection(text: str) -> bool:
    return bool(re.search(
        r"\b(lapse|mag-lapse|mahal|mahirap|budget|hulog|di ko kaya|hindi kaya|sayang|bank referral|bakit kailangan)\b",
        text, re.IGNORECASE
    ))


class PHBancassuranceAgent:
    """
    Stateful conversational agent for Philippines Bancassurance lead qualification.
    Communicates in authentic Taglish with respect markers.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.state = PHDialogueState.GREETING
        self.profile = PHLeadProfile()
        self.turn_count = 0
        self._awaiting: Optional[str] = None
        self._load_knowledge()

    def _load_knowledge(self):
        try:
            faq_path = PH_DOMAIN_DIR / "bancassurance_faqs_objections.md"
            self.faq_text = faq_path.read_text(encoding="utf-8") if faq_path.exists() else ""
            prod_path = PH_DOMAIN_DIR / "bancassurance_products.md"
            self.prod_text = prod_path.read_text(encoding="utf-8") if prod_path.exists() else ""
        except Exception as e:
            logger.warning(f"[PHAgent] Knowledge load error: {e}")
            self.faq_text = ""
            self.prod_text = ""

    def get_opening_message(self) -> str:
        return (
            "Magandang araw po! Ako po si Blessica mula sa HealthShield Bancassurance. "
            "Nakatanggap po kami ng inyong referral mula sa inyong bank branch para sa ating "
            "life protection and savings plans. May I have your name po muna para ma-address ko kayo nang maayos?"
        )

    def process(self, utterance: str) -> Tuple[str, Dict[str, Any]]:
        self.turn_count += 1
        utterance = utterance.strip()

        # Global escalation check (Taglish preserved)
        if _wants_ph_escalation(utterance) and self.state not in (
            PHDialogueState.ESCALATION, PHDialogueState.ENDED
        ):
            return self._escalate("Customer requested human bancassurance specialist.")

        if self.state == PHDialogueState.GREETING:
            response = self._handle_greeting(utterance)
        elif self.state == PHDialogueState.LEAD_QUALIFICATION:
            response = self._handle_qualification(utterance)
        elif self.state in (PHDialogueState.PRODUCT_INFO, PHDialogueState.OBJECTION_HANDLING):
            response = self._handle_product_and_objections(utterance)
        elif self.state == PHDialogueState.CLARIFICATION:
            response = self._handle_clarification(utterance)
        elif self.state == PHDialogueState.QUALIFICATION_DONE:
            response = self._handle_conclusion(utterance)
        elif self.state == PHDialogueState.ESCALATION:
            response = self._handle_escalation(utterance)
        else:
            response = "Maraming salamat po sa inyong tiwala sa HealthShield Bancassurance. Ingat po kayo lagi!"

        meta = {
            "state": self.state.value,
            "turn": self.turn_count,
            "market": "philippines",
            "language_mode": "taglish",
            "qualification_profile": self.profile.to_dict(),
            "ended": self.state == PHDialogueState.ENDED,
            "escalated": self.state == PHDialogueState.ESCALATION,
        }
        return response, meta

    def _handle_greeting(self, utterance: str) -> str:
        name = _extract_name(utterance)
        if name:
            self.profile.name = name
        self.state = PHDialogueState.LEAD_QUALIFICATION
        self._awaiting = "age"
        name_str = f", {self.profile.name}" if self.profile.name else ""
        return (
            f"Salamat po{name_str}! Para po masuri natin ang angkop na coverage para sa inyo, "
            "ilang taon na po kayo ngayon?"
        )

    def _handle_qualification(self, utterance: str) -> str:
        # Check early objection
        if _is_ph_objection(utterance):
            return self._handle_objection_response(utterance)

        # 1. Collect Age
        if self._awaiting == "age":
            age = _extract_age(utterance)
            if age:
                self.profile.age = age
                if age < 18 or age > 60:
                    self.profile.eligible = False
                    self.state = PHDialogueState.QUALIFICATION_DONE
                    return (
                        f"Salamat po sa pagbabahagi. Ayon po sa ating underwriting rules, "
                        f"ang individual bancassurance life plans po natin ay bukas para sa edad 18 hanggang 60 taon. "
                        f"Dahil {age} na po kayo, maaari po nating tingnan ang ating Senior Heritage options. "
                        "Gusto niyo po bang ikonekta ko kayo sa ating specialist para dito?"
                    )
                self.profile.eligible = True
                self._awaiting = "beneficiary"
                return (
                    f"Ayan, pasok po kayo sa standard issue tier para sa edad {age}! "
                    "Para po sa inyong life policy, sino po ang balak ninyong italaga bilang primary beneficiary? "
                    "Halimbawa po, ang inyong spouse, mga anak, o magulang?"
                )
            return "Pasensya na po, hindi ko po nakuha ang inyong edad. Ilang taon na po kayo?"

        # 2. Collect Beneficiary
        if self._awaiting == "beneficiary":
            self.profile.beneficiary_relation = utterance[:60]
            self._awaiting = "coverage"
            return (
                "Noted po! Napakagandang desisyon na protektahan ang kanilang kinabukasan. "
                "Anong uri po ng proteksyon ang mas gusto ninyo — guaranteed life protection na may ₱1,000,000 benefit, "
                "o 'yung may kasamang savings at endowment payouts?"
            )

        # 3. Collect Coverage Interest
        if self._awaiting == "coverage":
            self.profile.coverage_interest = utterance[:80]
            self.state = PHDialogueState.PRODUCT_INFO
            self._awaiting = None
            return (
                "Napakaganda po niyan! Ang aming Bancassurance Secure Life plan ay may guaranteed "
                "₱1,000,000 death benefit kasama ang ₱500,000 Accidental Death & Dismemberment rider. "
                "Nagsisimula lang po ito sa around ₱1,650 kada buwan via auto-debit sa inyong bank account. "
                "May mga katanungan po ba kayo tungkol sa benefits o sa inyong premium payment?"
            )

        return "May maitutulong pa po ba ako sa inyong plan options?"

    def _handle_product_and_objections(self, utterance: str) -> str:
        if _is_ph_objection(utterance):
            return self._handle_objection_response(utterance)

        # Check closing signal
        if _is_taglish_negative(utterance) and any(w in utterance.lower() for w in ["tanong", "question", "salamat", "okay", "ayos"]):
            return self._conclude_lead()

        if any(w in utterance.lower() for w in ["salamat", "thank", "ayos", "malinaw", "clear", "sounds good"]):
            return self._conclude_lead()

        # Grounded product / FAQ lookup in Taglish
        if "beneficiary" in utterance.lower():
            return (
                "Para po sa beneficiary designation, pwede niyo pong italaga ang inyong legal spouse, mga anak, o magulang. "
                "Kung minor pa po ang mga anak, maglalagay po tayo ng isang trusted adult trustee para protektado ang claim. "
                "May iba pa po ba kayong katanungan?"
            )

        if "rider" in utterance.lower() or "accident" in utterance.lower():
            return (
                "Opo, kasama na po sa ating Secure Life tier ang Accidental Death and Dismemberment (AD&D) rider "
                "na nagbibigay ng karagdagang ₱500,000 cash coverage kung sakaling magkaroon ng aksidente. "
                "Nais niyo po bang malaman ang payment options?"
            )

        if "lapse" in utterance.lower() or "delay" in utterance.lower() or "grace period" in utterance.lower():
            return (
                "Huwag po kayong mag-alala! Mayroon po tayong 31-day grace period mula sa premium due date. "
                "Kahit ma-delay po nang kaunti ang bayad, active pa rin po ang buong ₱1,000,000 coverage ninyo. "
                "Gusto niyo po bang i-setup ang monthly auto-debit para iwas-delay?"
            )

        # Safe fallback in Taglish
        return (
            "Ipagpaumanhin po ninyo, wala po sa aking verified bancassurance guidelines ang eksaktong detalye niyan. "
            "Gusto niyo po bang ikonekta ko kayo sa ating licensed bancassurance specialist sa inyong branch para masagot ito nang tama?"
        )

    def _handle_objection_response(self, utterance: str) -> str:
        self.state = PHDialogueState.OBJECTION_HANDLING
        utt_lower = utterance.lower()

        # Objection 1: Lapse risk / Budget concerns
        if "lapse" in utt_lower or "budget" in utt_lower or "ipit" in utt_lower:
            return (
                "Naiintindihan ko po ang inyong pag-aalala, Ma'am/Sir. "
                "Una po, may 31-day grace period po tayo sa bawat due date kaya hindi agad mag-la-lapse ang policy. "
                "Pangalawa po, may flexible auto-debit options tayo kung saan pwedeng gawing monthly ang hulog na nagsisimula "
                "lang sa ₱1,650 para hindi mabigat sa bulsa. "
                "Makatutulong po ba sa inyo ang ganitong monthly arrangement?"
            )

        # Objection 2: Affordability / Expensive
        if "mahal" in utt_lower or "di kaya" in utt_lower or "mabigat" in utt_lower:
            return (
                "Nauunawaan ko po kayo nang lubos. Kaya nga po may auto-debit facility tayo sa inyong bank account "
                "para pwedeng humigit-kumulang ₱55 pesos lang kada araw ang katumbas ng hulog para sa ₱1,000,000 guaranteed life protection ng inyong pamilya. "
                "Gusto niyo po bang tingnan natin ang quarterly o monthly computation?"
            )

        # Objection 3: Bank referral necessity
        if "bank" in utt_lower or "referral" in utt_lower:
            return (
                "Magandang tanong po! Dahil po galing kayo sa branch referral ng ating partner bank, "
                "may exclusive discounted rates po kayo at simplified underwriting nang walang required medical check-up para sa planong ito. "
                "Gusto niyo po bang ituloy natin ang application?"
            )

        return (
            "Naiintindihan ko po ang inyong punto, Ma'am/Sir. Mayroon po tayong flexible arrangements para masigurong "
            "akma ang policy sa inyong kasalukuyang financial capacity. Nais niyo po bang talakayin natin ang mga detalye?"
        )

    def _handle_clarification(self, utterance: str) -> str:
        if _is_taglish_affirmative(utterance):
            self.state = PHDialogueState.PRODUCT_INFO
            return (
                "Salamat po! Maaari po nating simulan ang inyong application para sa monthly auto-debit option. "
                "May iba pa po ba kayong katanungan bago natin i-finalize ang inyong referral record?"
            )
        return self._handle_product_and_objections(utterance)

    def _handle_conclusion(self, utterance: str) -> str:
        self.state = PHDialogueState.ENDED
        return (
            "Maraming salamat po sa inyong oras, Ma'am/Sir! Naitala ko na po ang inyong bancassurance lead profile. "
            "Makikipag-ugnayan po ang ating branch advisor para sa inyong policy schedule. Magandang araw po!"
        )

    def _conclude_lead(self) -> str:
        self.state = PHDialogueState.QUALIFICATION_DONE
        name_str = f", {self.profile.name}" if self.profile.name else ""
        return (
            f"Napakagaling po{name_str}! Kuwalipikado po kayo para sa ating HealthShield Bancassurance Secure Life plan. "
            "I-fo-forward ko po ang inyong impormasyon sa inyong partner bank branch para maasikaso ang inyong welcome kit at policy papers. "
            "May pahabol pa po ba kayong tanong?"
        )

    def _handle_escalation(self, utterance: str) -> str:
        self.state = PHDialogueState.ENDED
        return (
            "Opo, agad ko po kayong ikokonekta sa isa sa ating mga lisensyadong bancassurance specialists. "
            "Paki-hintay lang po sandali sa linya, Ma'am/Sir. Maraming salamat po!"
        )

    def _escalate(self, reason: str) -> Tuple[str, Dict[str, Any]]:
        self.state = PHDialogueState.ESCALATION
        response = (
            "Opo, naiintindihan ko po. I-co-connect ko po kayo agad sa isa sa ating licensed bancassurance specialists "
            "para matulungan po kayo nang personal. Sandali lang po, Ma'am/Sir."
        )
        meta = {
            "state": self.state.value,
            "turn": self.turn_count,
            "market": "philippines",
            "language_mode": "taglish",
            "qualification_profile": self.profile.to_dict(),
            "ended": False,
            "escalated": True,
            "escalation_reason": reason,
        }
        return response, meta
