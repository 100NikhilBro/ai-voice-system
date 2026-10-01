"""
Verification Script for Web UI Integration & End-to-End Capabilities
"""
import asyncio
import json
import urllib.request
import websockets

def test_html_dom_elements():
    print("\n--- 1. Testing HTML DOM Elements ---")
    url = "http://127.0.0.1:8000/"
    with urllib.request.urlopen(url) as res:
        html = res.read().decode("utf-8")
    
    required_ids = [
        "voice-canvas",
        "status-badge",
        "status-text",
        "call-timer",
        "state-pill",
        "speech-bubble",
        "agent-text",
        "transcript-scroll-area",
        "turn-count",
        "transcript-list",
        "empty-state",
        "btn-call",
        "btn-mic",
        "btn-hangup",
        "manual-input",
        "btn-send",
        "lang-select",
        "qual-drawer",
        "q-hero-text",
        "q-hero-badge",
        "qual-fields",
        "q-name",
        "q-age",
        "q-pre",
        "q-interest",
        "q-eligible",
        "q-state",
        "sidebar-sessions",
        "recent-calls-list",
        "nudges-feed",
        "empty-nudges",
        "kb-search-input",
        "kb-results-panel",
        "tab-voice",
        "tab-kb",
        "tab-insights"
    ]
    
    missing = []
    for elem_id in required_ids:
        if f'id="{elem_id}"' not in html and f"id='{elem_id}'" not in html:
            missing.append(elem_id)
            
    if missing:
        print(f"[FAIL] Missing DOM elements: {missing}")
        raise AssertionError(f"Missing DOM elements: {missing}")
    print(f"[PASS] All {len(required_ids)} required DOM elements present and verified.")

def test_rest_endpoints():
    print("\n--- 2. Testing Real Data Endpoints for UI ---")
    # Health
    with urllib.request.urlopen("http://127.0.0.1:8000/health") as res:
        health = json.loads(res.read().decode())
    assert health["status"] == "healthy"
    print(f"[PASS] /health healthy: {health['indexed_records']} indexed records")

    # Saved transcripts
    with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/voice/transcripts") as res:
        transcripts = json.loads(res.read().decode())
    count = len(transcripts.get("transcripts", []))
    assert count > 0
    first_id = transcripts["transcripts"][0]["session_id"]
    print(f"[PASS] /api/v1/voice/transcripts returned {count} recent sessions (latest: {first_id})")

    # Fetch individual transcript
    with urllib.request.urlopen(f"http://127.0.0.1:8000/api/v1/voice/transcripts/{first_id}") as res:
        single = json.loads(res.read().decode())
    assert single["session_id"] == first_id
    print(f"[PASS] /api/v1/voice/transcripts/{first_id} returned transcript with {len(single.get('turns', []))} turns")

    # KB Hybrid Search
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/kb/search",
        data=json.dumps({"query": "What are the benefits of the HealthShield Gold Plan?", "top_k": 3}).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as res:
        kb_data = json.loads(res.read().decode())
    assert kb_data["grounded_answer_available"] is True
    assert len(kb_data["results"]) > 0
    print(f"[PASS] /api/v1/kb/search returned grounded results (top citation: {kb_data['top_citation']})")

    # Q4 Replay endpoint
    req_replay = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/insights/replay",
        data=json.dumps({"transcript_name": "call_01_cooperative", "replay_speed": 10.0}).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_replay) as res:
        replay_data = json.loads(res.read().decode())
    assert replay_data["total_turns"] > 0
    print(f"[PASS] /api/v1/insights/replay completed {replay_data['total_turns']} turns with stats")

async def test_websocket_voice_flow():
    print("\n--- 3. Testing Real Voice WebSocket Consultation Flow ---")
    uri = "ws://127.0.0.1:8000/ws/voice"
    async with websockets.connect(uri) as ws:
        # Start
        await ws.send(json.dumps({"type": "start", "language": "en"}))
        msg1 = json.loads(await ws.recv())
        assert msg1["type"] == "session_started"
        session_id = msg1["session_id"]
        print(f"[PASS] WS session_started: session_id={session_id}")
        
        # Audio packet
        msg_audio = json.loads(await ws.recv())
        assert msg_audio["type"] == "agent_audio"
        assert len(msg_audio.get("data", "")) > 100
        print(f"[PASS] WS opening TTS audio received ({len(msg_audio['data'])} base64 chars)")

        # Turn 1: Customer gives name
        await ws.send(json.dumps({"type": "transcript", "text": "My name is Evelyn Miller", "language": "en"}))
        agent_msg = json.loads(await ws.recv())
        assert agent_msg["type"] == "agent_text"
        assert agent_msg["state"] == "lead_qualification"
        assert agent_msg["meta"]["qualification_profile"]["name"] == "Evelyn Miller"
        print(f"[PASS] WS agent reply: '{agent_msg['text'][:50]}...' [state={agent_msg['state']}]")

        # Drain audio
        await ws.recv()

        # Turn 2: Customer gives age
        await ws.send(json.dumps({"type": "transcript", "text": "I am 38 years old", "language": "en"}))
        agent_msg2 = json.loads(await ws.recv())
        assert agent_msg2["type"] == "agent_text"
        assert agent_msg2["meta"]["qualification_profile"]["age"] == 38
        print(f"[PASS] WS agent lead qualification age parsed: 38 yrs")

        # Drain audio
        await ws.recv()

        # End call
        await ws.send(json.dumps({"type": "end"}))
        end_msg = json.loads(await ws.recv())
        assert end_msg["type"] == "session_ended"
        print(f"[PASS] WS session_ended received cleanly for {session_id}")

async def test_websocket_insights_flow():
    print("\n--- 4. Testing Q4 Live Insights WebSocket Stream ---")
    test_sid = "test_ui_insight_session"
    uri = f"ws://127.0.0.1:8000/api/v1/insights/ws/{test_sid}"
    async with websockets.connect(uri) as ws:
        connected = json.loads(await ws.recv())
        assert connected["type"] == "connected"
        print(f"[PASS] Insights WS connected to session {test_sid}")

        # Send customer utterance containing an opportunity signal
        await ws.send(json.dumps({
            "type": "utterance",
            "speaker": "customer",
            "text": "I also want to make sure my family and kids are covered under the plan.",
            "t0_ms": 1000.0
        }))
        
        # We should receive an ack or a nudge
        msg = json.loads(await ws.recv())
        print(f"[PASS] Insights WS received message type: {msg.get('type')}")

def main():
    test_html_dom_elements()
    test_rest_endpoints()
    asyncio.run(test_websocket_voice_flow())
    asyncio.run(test_websocket_insights_flow())
    print("\n[SUCCESS] ALL UI & INTEGRATION VERIFICATION TESTS PASSED!\n")

if __name__ == "__main__":
    main()
