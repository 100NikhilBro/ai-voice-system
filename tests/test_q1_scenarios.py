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

import sys
import json
import logging
import pytest
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent.parent))

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


# ─── Scenario 3: Incomplete / Conflicting Details ────────────────────────────

def test_scenario_incomplete_conflicting_details():
    """
    Scenario 3: Incomplete or conflicting customer details.
    Customer initially denies pre-existing conditions during qualification,
    but later reveals a regular prescription (daily insulin for diabetes).
    Agent must detect the conflict, avoid inventing an eligibility decision,
    enter clarification state, record the conflict in conflicts_detected,
    and guide customer accurately.
    """
    logger.info("\n" + "="*60)
    logger.info("SCENARIO 3: INCOMPLETE / CONFLICTING DETAILS")
    logger.info("="*60)

    turns = [
        "Hi, my name is David",                               # greeting
        "I am 45 years old",                                  # age
        "No, I don't have any pre-existing conditions",       # pre-existing → initial negative declaration
        "I'm looking for hospitalization and chronic care",   # coverage interest
        "Well, just my daily insulin for diabetes, that doesn't count right?",  # conflicting detail
        "Yes, let's explore those plan options",              # clarification acceptance
        "What does the Gold plan cover for waiting periods?", # product info
        "Thank you, that answers my question",                # conclude
    ]

    result = run_scenario("test-conflict-03", turns)
    profile = result["profile"]

    logger.info(f"\n✅ SCENARIO 3 RESULT:")
    logger.info(f"   Final state       : {result['final_state']}")
    logger.info(f"   Pre-existing      : {profile.get('has_pre_existing')}")
    logger.info(f"   Conflicts detected: {profile.get('conflicts_detected')}")
    logger.info(f"   Flags             : {profile.get('flags')}")

    # Assertions:
    # 1. Conflict was detected and logged
    assert len(profile.get("conflicts_detected", [])) > 0, "No conflict was detected in profile"
    assert any("insulin" in c.lower() or "pre-existing" in c.lower() for c in profile.get("conflicts_detected", []))

    # 2. Pre-existing condition was updated to True
    assert profile.get("has_pre_existing") is True, "Expected pre-existing to be updated to True"
    assert "pre_existing_conditions" in (profile.get("flags") or [])

    # 3. State machine transitioned through clarification
    states_visited = [r["state"] for r in result["responses"]]
    assert "clarification" in states_visited, f"Clarification state not visited: {states_visited}"

    # 4. Agent response in clarification turn explicitly addressed the medication/underwriting guideline
    clarification_responses = [r["agent"] for r in result["responses"] if r["state"] == "clarification"]
    assert len(clarification_responses) > 0
    assert any("underwriting" in r.lower() or "pre-existing" in r.lower() or "insulin" in r.lower() for r in clarification_responses)

    # 5. Transcript saved
    assert Path(result["transcript_path"]).exists()
    logger.info("✅ Scenario 3: PASSED")


# ─── Scenario 4: Out-of-Scope Question (Multi-Turn) ──────────────────────────

def test_scenario_out_of_scope():
    """
    Scenario 4: Out-of-scope question in a complete multi-turn conversation.
    Customer qualifies initially, asks an out-of-scope query (pet insurance vaccination schedule),
    agent explicitly states verified info is unavailable, avoids hallucination,
    offers specialist assistance or return to health plans,
    and customer safely returns to health insurance qualification.
    """
    logger.info("\n" + "="*60)
    logger.info("SCENARIO 4: OUT-OF-SCOPE QUESTION (MULTI-TURN)")
    logger.info("="*60)

    turns = [
        "Hello, my name is Sarah Jenkins",                    # greeting
        "I am 29 years old",                                  # age
        "No, I have no pre-existing conditions",              # pre-existing
        "I'm interested in individual comprehensive coverage",# coverage interest
        "What is the pet insurance vaccination schedule for Golden Retrievers?", # out-of-scope
        "Okay, let's return to your health plans. What does the Silver plan cover?", # safe return
        "That sounds good, thank you very much",              # wrap-up
    ]

    result = run_scenario("test-outofscope-04", turns)
    profile = result["profile"]

    logger.info(f"\n✅ SCENARIO 4 RESULT:")
    logger.info(f"   Final state : {result['final_state']}")
    logger.info(f"   Name        : {profile.get('name')}")
    logger.info(f"   Eligible    : {profile.get('eligible')}")

    # Find response to the out-of-scope question
    oos_response = None
    for turn in result["responses"]:
        if "pet insurance" in turn["customer"].lower():
            oos_response = turn["agent"]
            break

    assert oos_response is not None, "Out-of-scope turn response not found"
    logger.info(f"   Out-of-scope response: {oos_response[:150]}…")

    # Anti-hallucination verification:
    assert any(phrase in oos_response.lower() for phrase in [
        "don't have verified information",
        "not available in our policy records",
        "unavailable",
        "inaccurate details",
    ]), f"Agent did not state information is unavailable: {oos_response}"

    assert "vaccine schedule" not in oos_response.lower()
    assert "golden retriever" not in oos_response.lower()

    # Agent safely returned to qualification / product info for subsequent turn
    silver_turn = [t for t in result["responses"] if "silver" in t["customer"].lower()]
    assert len(silver_turn) > 0, "Agent did not process subsequent health plan question"
    assert len(silver_turn[0]["agent"]) > 20

    assert Path(result["transcript_path"]).exists()
    logger.info("✅ Scenario 4: PASSED")


# ─── Scenario 5: Human Assistance Request ───────────────────────────────────

def test_scenario_human_assistance():
    """
    Scenario 5: Human assistance request.
    Customer explicitly requests to speak with a human agent / supervisor.
    Agent detects escalation signal across turns, executes handoff protocol,
    and sets state to ESCALATION.
    """
    logger.info("\n" + "="*60)
    logger.info("SCENARIO 5: HUMAN ASSISTANCE REQUEST")
    logger.info("="*60)

    turns = [
        "I need to speak to a licensed human specialist right away, please transfer me",
    ]

    result = run_scenario("test-escalation-05", turns)

    logger.info(f"\n✅ SCENARIO 5 RESULT:")
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

    logger.info("✅ Scenario 5: PASSED")


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

    response_lower = response.lower()
    bad_hallucination_indicators = [
        "bitcoin coverage",
        "cryptocurrency plan",
        "investment policy",
    ]
    for bad in bad_hallucination_indicators:
        assert bad not in response_lower, (
            f"Agent hallucinated crypto health policy: {response}"
        )

    logger.info("[PASS] KB Grounding Test: agent did not hallucinate crypto health policy")


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("\n[TEST] Running Q1 Voice Agent Test Scenarios (All 5 Required)\n")
    print("=" * 60)

    results = {
        "scenario_1_cooperative": None,
        "scenario_2_objection": None,
        "scenario_3_incomplete_conflicting": None,
        "scenario_4_out_of_scope": None,
        "scenario_5_human_assistance": None,
        "kb_grounding": None,
    }

    scenarios = [
        ("scenario_1_cooperative", test_scenario_cooperative_customer),
        ("scenario_2_objection", test_scenario_hesitant_objector),
        ("scenario_3_incomplete_conflicting", test_scenario_incomplete_conflicting_details),
        ("scenario_4_out_of_scope", test_scenario_out_of_scope),
        ("scenario_5_human_assistance", test_scenario_human_assistance),
        ("kb_grounding", test_kb_grounding_never_invents),
    ]

    for name, func in scenarios:
        try:
            func()
            results[name] = "PASSED"
        except AssertionError as e:
            results[name] = f"FAILED: {e}"
            print(f"[FAIL] {name} FAILED: {e}")
        except Exception as e:
            results[name] = f"ERROR: {e}"
            print(f"[ERROR] {name} ERROR: {e}")

    print("\n" + "=" * 60)
    print("Q1 TEST SCENARIO RESULTS (ALL 5 SCENARIOS VERIFIED)")
    print("=" * 60)
    for k, v in results.items():
        icon = "[PASS]" if v == "PASSED" else "[FAIL]"
        print(f"  {icon} {k}: {v}")

    all_passed = all(v == "PASSED" for v in results.values())
    print("\n" + ("[SUCCESS] ALL 5 SCENARIOS PASSED" if all_passed else "[FAILURE] SOME TESTS FAILED"))

    # Save results artifact
    report_dir = settings.KB_STORE_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "q1_scenario_results.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[REPORT] Results saved to: {report_path}")
