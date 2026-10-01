"""
End-to-End Verification Script for Q1 Frontend & Voice Call Lifecycle
=====================================================================
Validates:
  1. Web UI loads with HTTP 200 and all required DOM IDs for the redesigned UI
  2. Start Call WS lifecycle initiates session & opening greeting
  3. Audio MP3 bytes received for TTS synthesis
  4. Customer utterance sent (testing voice/text input fallback)
  5. Agent response generated and received
  6. Qualification profile state updates dynamically
  7. End Call terminates cleanly and generates saved conversation transcript
  8. Transcript API retrieves the completed session
"""

import asyncio
import json
import re
from pathlib import Path
import httpx
import websockets

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws/voice"

REQUIRED_DOM_IDS = [
    "status-badge",
    "status-text",
    "state-pill",
    "call-timer",
    "lang-select",
    "btn-call",
    "btn-mic",
    "btn-hangup",
    "btn-send",
    "manual-input",
    "voice-canvas",
    "speech-bubble",
    "agent-text",
    "transcript-list",
    "turn-count",
    "qual-drawer",
    "qual-fields",
    "q-name",
    "q-age",
    "q-pre",
    "q-interest",
    "q-eligible",
    "q-state",
    "toast-container",
]

async def verify_frontend_html():
    print("\n--- 1. Verifying Frontend HTML & DOM IDs ---")
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        html = resp.text

    assert "<title>HealthShield AI — Voice Agent</title>" in html
    assert "voice-canvas" in html

    missing_ids = []
    for dom_id in REQUIRED_DOM_IDS:
        if f'id="{dom_id}"' not in html:
            missing_ids.append(dom_id)

    if missing_ids:
        print(f"FAILED: Missing DOM IDs: {missing_ids}")
        return False
    print(f"SUCCESS: All {len(REQUIRED_DOM_IDS)} required DOM IDs present in redesigned UI!")
    return True

async def verify_voice_call_flow():
    print("\n--- 2. Verifying Voice Call WebSocket Flow ---")
    async with websockets.connect(WS_URL) as ws:
        # Step A: Start Call
        print("Sending {type: start}...")
        await ws.send(json.dumps({"type": "start", "language": "en"}))

        # Expect session_started
        msg1 = json.loads(await ws.recv())
        print(f"Received msg1: type={msg1.get('type')}, session_id={msg1.get('session_id')}")
        assert msg1.get("type") == "session_started", f"Unexpected msg: {msg1}"
        session_id = msg1["session_id"]
        assert "HealthShield" in msg1.get("opening", "")

        # Expect agent_audio (opening TTS)
        msg2 = json.loads(await ws.recv())
        print(f"Received msg2: type={msg2.get('type')}, mime={msg2.get('mime')}, audio_len={len(msg2.get('data', ''))}")
        assert msg2.get("type") == "agent_audio"
        assert len(msg2.get("data", "")) > 100

        # Step B: Customer Turn 1 (Name)
        print("\nSending customer turn 1 (Name: Maria Santos)...")
        await ws.send(json.dumps({"type": "transcript", "text": "My name is Maria Santos", "language": "en"}))
        msg3 = json.loads(await ws.recv())
        print(f"Received agent_text turn 1: state={msg3.get('state')}, text={msg3.get('text')[:75]}...")
        assert msg3.get("type") == "agent_text"
        qual1 = msg3.get("meta", {}).get("qualification_profile", {})
        print(f"Updated Qualification Profile (Turn 1): {qual1}")
        assert qual1.get("name") == "Maria Santos"

        msg4 = json.loads(await ws.recv())
        assert msg4.get("type") == "agent_audio"
        print(f"Received agent_audio turn 1: bytes={len(msg4.get('data', ''))}")

        # Step C: Customer Turn 2 (Age)
        print("\nSending customer turn 2 (Age: 35)...")
        await ws.send(json.dumps({"type": "transcript", "text": "I am 35 years old", "language": "en"}))
        msg5 = json.loads(await ws.recv())
        print(f"Received agent_text turn 2: state={msg5.get('state')}, text={msg5.get('text')[:75]}...")
        qual2 = msg5.get("meta", {}).get("qualification_profile", {})
        print(f"Updated Qualification Profile (Turn 2): {qual2}")
        assert qual2.get("age") == 35

        msg6 = json.loads(await ws.recv())
        assert msg6.get("type") == "agent_audio"

        # Step D: Customer Turn 3 (Pre-existing)
        print("\nSending customer turn 3 (No pre-existing)...")
        await ws.send(json.dumps({"type": "transcript", "text": "No, I don't have any pre-existing conditions", "language": "en"}))
        msg7 = json.loads(await ws.recv())
        print(f"Received agent_text turn 3: state={msg7.get('state')}, text={msg7.get('text')[:75]}...")
        qual3 = msg7.get("meta", {}).get("qualification_profile", {})
        print(f"Updated Qualification Profile (Turn 3): {qual3}")
        assert qual3.get("has_pre_existing") is False

        msg8 = json.loads(await ws.recv())
        assert msg8.get("type") == "agent_audio"

        # Step E: Customer Turn 4 (Coverage interest & KB question)
        print("\nSending customer turn 4 (Coverage interest)...")
        await ws.send(json.dumps({"type": "transcript", "text": "I'm interested in comprehensive hospitalization coverage. What are the benefits of the Gold plan?", "language": "en"}))
        msg9 = json.loads(await ws.recv())
        print(f"Received agent_text turn 4: state={msg9.get('state')}, text={msg9.get('text')[:75]}...")
        qual4 = msg9.get("meta", {}).get("qualification_profile", {})
        print(f"Updated Qualification Profile (Turn 4): {qual4}")
        assert qual4.get("has_pre_existing") is False

        msg10 = json.loads(await ws.recv())
        assert msg10.get("type") == "agent_audio"

        # Step F: Customer Turn 5 (No more questions -> concludes qualification)
        print("\nSending customer turn 5 (No more questions, thank you)...")
        await ws.send(json.dumps({"type": "transcript", "text": "No more questions, thank you!", "language": "en"}))
        msg11 = json.loads(await ws.recv())
        print(f"Received agent_text turn 5: state={msg11.get('state')}, text={msg11.get('text')[:75]}...")
        qual5 = msg11.get("meta", {}).get("qualification_profile", {})
        print(f"Updated Qualification Profile (Turn 5): {qual5}")
        assert qual5.get("eligible") is True
        assert msg11.get("state") == "qualification_done"

        msg12 = json.loads(await ws.recv())
        assert msg12.get("type") == "agent_audio"

        # Step D: End Call
        print("\nSending {type: end} (simulating End Call button click)...")
        await ws.send(json.dumps({"type": "end"}))

        msg7 = json.loads(await ws.recv())
        print(f"Received session_ended: type={msg7.get('type')}, transcript_path={msg7.get('transcript_path')}")
        assert msg7.get("type") == "session_ended"

    # Step E: Verify Transcript API
    print("\n--- 3. Verifying Saved Transcript API ---")
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/api/v1/voice/transcripts/{session_id}")
        assert resp.status_code == 200, f"Failed to get transcript: {resp.status_code}"
        transcript_data = resp.json()
        print(f"Retrieved transcript turns count: {len(transcript_data.get('turns', []))}")
        assert len(transcript_data.get("turns", [])) >= 4
        print("Transcript turns:")
        for t in transcript_data["turns"]:
            print(f"  [{t['speaker'].upper()}]: {t['text'][:65]}...")

    print("\n========================================================")
    print("ALL Q1 REDESIGN VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("========================================================")
    return True

async def main():
    ok1 = await verify_frontend_html()
    ok2 = await verify_voice_call_flow()
    if not (ok1 and ok2):
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
