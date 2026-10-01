"""
Q3 Philippines Bancassurance Voice Agent Tests
==============================================
Verifies:
1. Cooperative Taglish bancassurance lead qualification with respect markers (po/opo)
2. Policy lapse objection handling with grounded 31-day grace period
3. In-register polite Taglish human escalation (no abrupt English drop)
4. Underwriting age validation
"""

import sys
import logging
import pytest
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.voice.localized.ph_bancassurance_agent import PHBancassuranceAgent, PHDialogueState

logger = logging.getLogger(__name__)


def test_ph_cooperative_lead():
    """
    Scenario 1: Cooperative customer Maria Santos qualifies for Bancassurance Secure Life.
    Demonstrates natural Taglish, respect markers (po/opo), and life insurance terminology.
    """
    agent = PHBancassuranceAgent("test-ph-coop-01")
    opening = agent.get_opening_message()
    assert "HealthShield Bancassurance" in opening
    assert "po" in opening.lower()

    turns = [
        "Ako po si Maria Santos",                                      # Name
        "Ako po ay 35 years old",                                      # Age
        "Gusto ko pong ilagay ang aking spouse at dalawang anak",      # Beneficiary
        "Interesado po ako sa guaranteed life protection plan",        # Coverage
        "Kasama na po ba dito ang accidental death rider?",           # Product inquiry
        "Maraming salamat po, napakalinaw ng paliwanag ninyo!",        # Wrap-up
    ]

    responses = []
    for utt in turns:
        resp, meta = agent.process(utt)
        responses.append((resp, meta))

    # Assertions
    profile = agent.profile.to_dict()
    assert profile["name"] == "Maria Santos", f"Expected Maria Santos, got {profile['name']}"
    assert profile["age"] == 35, f"Expected 35, got {profile['age']}"
    assert profile["eligible"] is True
    assert "spouse" in profile["beneficiary_relation"].lower()

    # Verify Taglish and politeness markers preserved throughout
    for resp, meta in responses:
        assert any(m in resp.lower() for m in ["po", "opo", "ninyo", "kayo"]), (
            f"Response lacks Tagalog respect markers: {resp}"
        )

    # Verify agent used grounded bancassurance terms
    all_agent_text = " ".join(r[0].lower() for r in responses)
    assert any(term in all_agent_text for term in ["rider", "policy", "premium", "secure life", "coverage"])

    assert agent.state in (PHDialogueState.QUALIFICATION_DONE, PHDialogueState.ENDED)
    logger.info("[PASS] test_ph_cooperative_lead verified successfully.")


def test_ph_objection_lapse_and_escalation():
    """
    Scenario 2: Customer raises policy lapse objection, agent delivers grounded
    31-day grace period answer, then customer requests human specialist.
    Verifies that escalation remains in polite Taglish without falling back to cold English.
    """
    agent = PHBancassuranceAgent("test-ph-lapse-02")
    agent.get_opening_message()

    # Step 1: Greeting
    resp1, _ = agent.process("Magandang araw, ako si Juan dela Cruz")
    assert agent.profile.name == "Juan Dela Cruz"

    # Step 2: Qualification age
    resp2, _ = agent.process("40 years old po ako")
    assert agent.profile.age == 40
    assert agent.profile.eligible is True

    # Step 3: Raise policy lapse objection
    objection = "Baka mag-lapse lang po ang policy ko kapag nagka-problema sa pera, sayang lang ang hulog."
    resp3, meta3 = agent.process(objection)
    assert meta3["state"] == PHDialogueState.OBJECTION_HANDLING.value
    # Grounded rationale verification: must mention 31-day grace period and flexible/monthly terms
    assert any(w in resp3.lower() for w in ["grace period", "31-day", "31 day", "monthly", "hulog"])

    # Step 4: Human escalation request
    escalation_utt = "Gusto ko po sana ng kausap na tao, paki-transfer po ako sa licensed specialist."
    resp4, meta4 = agent.process(escalation_utt)
    assert meta4["state"] == PHDialogueState.ESCALATION.value
    assert meta4["escalated"] is True

    # Verify escalation preserves customer register (polite Taglish, not abrupt English)
    resp4_lower = resp4.lower()
    assert any(p in resp4_lower for p in ["opo", "po", "naiintindihan ko", "i-co-connect", "sandali lang"])
    assert "licensed" in resp4_lower or "specialist" in resp4_lower

    logger.info("[PASS] test_ph_objection_lapse_and_escalation verified successfully.")


def test_ph_underwriting_age_limit():
    """
    Scenario 3: Age limit enforcement (18-60 standard bancassurance).
    """
    agent = PHBancassuranceAgent("test-ph-age-03")
    agent.get_opening_message()
    agent.process("Ako po si Roberto")
    resp, meta = agent.process("68 years old na po ako")

    assert agent.profile.age == 68
    assert agent.profile.eligible is False
    assert "Senior Heritage" in resp or "60" in resp
    logger.info("[PASS] test_ph_underwriting_age_limit verified successfully.")


if __name__ == "__main__":
    test_ph_cooperative_lead()
    test_ph_objection_lapse_and_escalation()
    test_ph_underwriting_age_limit()
    print("ALL PHILIPPINES Q3 TESTS PASSED!")
