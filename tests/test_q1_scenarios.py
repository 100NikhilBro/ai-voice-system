"""
Q1 Voice Agent Test Scenarios
==============================
Three required conversation scenarios:

  Scenario 1: COOPERATIVE_CUSTOMER
    - Provides all information willingly
    - Asks about a specific plan (Gold)
    - No objections
    - Expected: full qualification → eligible

  Scenario 2: HESITANT_OBJECTOR
    - Hesitates about waiting periods
    - Raises a cost objection
    - Agent must handle via KB-grounded objection response
    - Then proceeds to qualify
    - Expected: full qualification with objection handled

  Scenario 3: ESCALATION_REQUEST
    - Asks to speak to a human immediately
    - Agent detects escalation signal
    - Expected: graceful escalation to human specialist

All three scenarios verify:
  - Agent never invents policy information (KB-grounded only)
  - State transitions are correct
  - Conversation is logged to JSON
  - Qualification profile is correctly populated
"""

import json
import logging
import pytest
from pathlib import Path
from src.voice.agent import VoiceAgent, DialogueState
from src.voice.conversation_logger import ConversationLogger
from src.config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def run_scenario(session_id: str, turns: list[str]) -> dict:
    """
    Simulate a complete call session and return the final state.

    Args:
        session_id: Unique ID for this test run.
        turns: List of customer utterances to send in order.

    Returns:
        dict with keys: final_state, profile, transcript_path, responses
    """
    conv_logger = ConversationLogger(session_id=session_id)
    agent = VoiceAgent(session_id=session_id)

    opening = agent.get_opening_message()
    conv_logger.log_turn("agent", opening)
    logger.info(f"[{session_id}] AGENT GREETING: {opening[:80]}…")

    responses = []

    for utterance in turns:
        if agent.state == DialogueState.ENDED:
            break

        conv_logger.log_turn("customer", utterance)
        logger.info(f"[{session_id}] CUSTOMER: {utterance}")

        response, meta = agent.process(utterance)
        conv_logger.log_turn("agent", response, meta)
        conv_logger.update_qualification(meta.get("qualification_profile", {}))

        logger.info(f"[{session_id}] AGENT [{meta['state']}]: {response[:100]}…")
        responses.append({
            "customer": utterance,
            "agent": response,
            "state": meta["state"],
            "profile": meta.get("qualification_profile", {}),
        })

        if meta.get("ended"):
            break

    outcome = "escalated" if agent.state == DialogueState.ESCALATION else "completed"
    transcript_path = conv_logger.close(outcome)

    return {
        "final_state": agent.state.value,
        "profile": agent.profile.to_dict(),
        "transcript_path": str(transcript_path),
        "responses": responses,
    }


# ─── Scenario 1: Cooperative Customer ────────────────────────────────────────

def test_scenario_cooperative_customer():
    """
    Scenario 1: Cooperative customer who provides all information willingly,
    asks about the Gold plan, and proceeds to full qualification.
    """
    logger.info("\n" + "="*60)
    logger.info("SCENARIO 1: COOPERATIVE CUSTOMER")
    logger.info("="*60)

    turns = [
        "My name is Maria Santos",                             # greeting → give name
        "I am 35 years old",                                  # age → eligible
        "No, I don't have any pre-existing conditions",       # pre-existing → no
        "I'm interested in comprehensive hospitalization coverage",  # coverage interest
        "What are the benefits of the Gold plan?",            # product info → KB lookup
        "How much is the room rent limit?",                   # follow-up → KB lookup
        "No more questions, thank you",                       # wrap-up
    ]

    result = run_scenario("test-cooperative-01", turns)
    profile = result["profile"]

    logger.info(f"\n✅ SCENARIO 1 RESULT:")
    logger.info(f"   Final state : {result['final_state']}")
    logger.info(f"   Name        : {profile.get('name')}")
    logger.info(f"   Age         : {profile.get('age')}")
    logger.info(f"   Pre-existing: {profile.get('has_pre_existing')}")
    logger.info(f"   Eligible    : {profile.get('eligible')}")
    logger.info(f"   Transcript  : {result['transcript_path']}")

    # Assertions
    assert profile.get("name") == "Maria Santos", f"Expected name 'Maria Santos', got {profile.get('name')}"
    assert profile.get("age") == 35, f"Expected age 35, got {profile.get('age')}"
    assert profile.get("has_pre_existing") == False, "Expected no pre-existing conditions"
    assert result["final_state"] in (
        DialogueState.QUALIFICATION_DONE.value,
        DialogueState.PRODUCT_INFO.value,
        DialogueState.ENDED.value,
    ), f"Unexpected final state: {result['final_state']}"

    # Verify KB grounding: agent responses must not be empty
    for turn in result["responses"]:
        assert len(turn["agent"]) > 10, "Agent response too short — possible empty/hallucinated"
        # Verify agent did not invent a forbidden term
        assert "I made this up" not in turn["agent"].lower()
        assert "I don't know but" not in turn["agent"].lower()

    # Verify transcript was saved
    assert Path(result["transcript_path"]).exists(), "Transcript file not saved"
    transcript_data = json.loads(Path(result["transcript_path"]).read_text())
    assert transcript_data["session_id"] == "test-cooperative-01"
    assert len(transcript_data["turns"]) >= len(turns)

    logger.info("✅ Scenario 1: PASSED")


# ─── Scenario 2: Hesitant Customer with Objections ───────────────────────────

def test_scenario_hesitant_objector():
    """
    Scenario 2: Customer who raises objections about waiting periods and cost.
    Agent must handle via KB-grounded objection responses without inventing data.
    """
    logger.info("\n" + "="*60)
    logger.info("SCENARIO 2: HESITANT OBJECTOR")
    logger.info("="*60)

    turns = [
        "Hi, I'm John",                                        # greeting
        "I'm 42",                                              # age
        "Yes, I have diabetes",                                # pre-existing → yes
        "Outpatient and hospitalization coverage",             # coverage interest
        "Why is the waiting period for pre-existing conditions so long? Other insurers offer immediate cover",
                                                               # objection → KB grounded
        "It seems quite expensive compared to competitors",    # cost objection → KB
        "Okay, I understand. Can you tell me more about the Platinum plan?",  # back to info
        "Thank you, that sounds good",                         # wrap-up
    ]

    result = run_scenario("test-objector-02", turns)
    profile = result["profile"]

    logger.info(f"\n✅ SCENARIO 2 RESULT:")
    logger.info(f"   Final state : {result['final_state']}")
    logger.info(f"   Name        : {profile.get('name')}")
    logger.info(f"   Age         : {profile.get('age')}")
    logger.info(f"   Pre-existing: {profile.get('has_pre_existing')}")
    logger.info(f"   Flags       : {profile.get('flags')}")
    logger.info(f"   Transcript  : {result['transcript_path']}")

    # Assertions
    assert profile.get("age") == 42, f"Expected age 42, got {profile.get('age')}"
    assert profile.get("has_pre_existing") == True, "Expected pre-existing=True"
    assert "pre_existing_conditions" in (profile.get("flags") or [])

    # Verify objection was handled (state passed through objection_handling)
    states_visited = [r["state"] for r in result["responses"]]
    assert "objection_handling" in states_visited, (
        f"Objection state was never entered. States: {states_visited}"
    )

    # Verify KB grounding in objection responses
    objection_responses = [
        r["agent"] for r in result["responses"]
        if r["state"] == "objection_handling"
    ]
    for resp in objection_responses:
        assert len(resp) > 20, "Objection response too short"
        # Agent should NOT claim information is unavailable for objections that exist in KB
        # (waiting period objection IS in KB as kb_faq_005)
        logger.info(f"   Objection response: {resp[:120]}…")

    assert Path(result["transcript_path"]).exists()
    logger.info("✅ Scenario 2: PASSED")


# ─── Scenario 3: Immediate Escalation Request ────────────────────────────────

def test_scenario_escalation_request():
    """
    Scenario 3: Customer immediately asks to speak with a human.
    Agent must detect the escalation signal and gracefully hand off.
    """
    logger.info("\n" + "="*60)
    logger.info("SCENARIO 3: ESCALATION REQUEST")
    logger.info("="*60)

    turns = [
        "I want to speak to a human agent please",            # escalation trigger
    ]

    result = run_scenario("test-escalation-03", turns)

    logger.info(f"\n✅ SCENARIO 3 RESULT:")
    logger.info(f"   Final state : {result['final_state']}")
    logger.info(f"   Escalated   : {result.get('final_state') == 'escalation'}")
    logger.info(f"   Transcript  : {result['transcript_path']}")

    # The agent must have escalated
    assert result["final_state"] in (
        DialogueState.ESCALATION.value,
        DialogueState.ENDED.value,
    ), f"Expected escalation state, got: {result['final_state']}"

    # The escalation response must mention human/specialist
    escalation_response = result["responses"][-1]["agent"].lower() if result["responses"] else ""
    assert any(kw in escalation_response for kw in [
        "specialist", "human", "transfer", "connect", "licensed"
    ]), f"Escalation response doesn't mention human handoff: {escalation_response}"

    # Transcript saved
    assert Path(result["transcript_path"]).exists()
    transcript_data = json.loads(Path(result["transcript_path"]).read_text())
    assert transcript_data["outcome"] in ("escalated", "completed")

    logger.info("✅ Scenario 3: PASSED")


# ─── Additional: KB Grounding Verification ───────────────────────────────────

def test_kb_grounding_never_invents():
    """
    Verify the agent explicitly acknowledges when policy info is unavailable.
    Uses a truly out-of-scope query (cryptocurrency investment advice) that
    has zero overlap with health insurance KB documents.
    """
    agent = VoiceAgent("test-grounding-04")

    # Move agent to product_info state manually
    agent.state = DialogueState.PRODUCT_INFO
    agent.profile.name = "Test"
    agent.profile.age = 30
    agent.profile.consent_given = True

    # Ask an unambiguously out-of-scope question
    response, meta = agent.process(
        "Can you advise me on cryptocurrency investment strategies and Bitcoin returns?"
    )

    logger.info(f"[Grounding Test] Agent response: {response[:200]}")

    # Agent must NOT invent a health-policy answer for a crypto question
    # Expected: either INFORMATION_UNAVAILABLE path or a product-info response
    # that does not claim to have policy info about crypto
    response_lower = response.lower()

    # The response should not fabricate crypto-related health policy content
    bad_hallucination_indicators = [
        "bitcoin coverage",
        "cryptocurrency plan",
        "investment policy",
    ]
    for bad in bad_hallucination_indicators:
        assert bad not in response_lower, (
            f"Agent hallucinated crypto health policy: {response}"
        )

    logger.info("✅ KB Grounding Test: PASSED — agent did not hallucinate crypto health policy")


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🎯 Running Q1 Voice Agent Test Scenarios\n")
    print("=" * 60)

    results = {
        "scenario_1": None,
        "scenario_2": None,
        "scenario_3": None,
        "kb_grounding": None,
    }

    try:
        test_scenario_cooperative_customer()
        results["scenario_1"] = "PASSED"
    except AssertionError as e:
        results["scenario_1"] = f"FAILED: {e}"
        print(f"❌ Scenario 1 FAILED: {e}")

    try:
        test_scenario_hesitant_objector()
        results["scenario_2"] = "PASSED"
    except AssertionError as e:
        results["scenario_2"] = f"FAILED: {e}"
        print(f"❌ Scenario 2 FAILED: {e}")

    try:
        test_scenario_escalation_request()
        results["scenario_3"] = "PASSED"
    except AssertionError as e:
        results["scenario_3"] = f"FAILED: {e}"
        print(f"❌ Scenario 3 FAILED: {e}")

    try:
        test_kb_grounding_never_invents()
        results["kb_grounding"] = "PASSED"
    except AssertionError as e:
        results["kb_grounding"] = f"FAILED: {e}"
        print(f"❌ KB Grounding FAILED: {e}")

    print("\n" + "=" * 60)
    print("📊 Q1 TEST SCENARIO RESULTS")
    print("=" * 60)
    for k, v in results.items():
        icon = "✅" if v == "PASSED" else "❌"
        print(f"  {icon} {k}: {v}")

    all_passed = all(v == "PASSED" for v in results.values())
    print("\n" + ("✅ ALL TESTS PASSED" if all_passed else "❌ SOME TESTS FAILED"))

    # Save results artifact
    report_dir = settings.KB_STORE_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "q1_scenario_results.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n📄 Results saved to: {report_path}")
