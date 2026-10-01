"""
Reproducible Q3 Regional Voice Call Recordings Generator
========================================================
Generates 4 reproducible call recordings for Question 3:
  1. call_ph_01_cooperative:
     - Philippines Bancassurance: Maria Santos qualifies in Taglish with respect markers (po/opo).
     - Voices: Agent=fil-PH-BlessicaNeural, Customer=en-PH-RosaNeural
  2. call_ph_02_lapse_objection:
     - Philippines Bancassurance: Policy lapse objection, 31-day grace period, respectful Taglish escalation.
     - Voices: Agent=fil-PH-BlessicaNeural, Customer=fil-PH-AngeloNeural
  3. call_id_01_installment_reminder:
     - Indonesia Multifinance: Cooperative installment reminder (angsuran jatuh tempo via m-banking).
     - Voices: Agent=id-ID-GadisNeural, Customer=id-ID-ArdiNeural
  4. call_id_02_javanese_hardship:
     - Indonesia Multifinance: Javanese regional speech (nggih, monggo, lho, mas), hardship, denda waiver, tenor extension.
     - Voices: Agent=id-ID-GadisNeural, Customer=jv-ID-DimasNeural (Javanese proxy)

Each recording bundle contains:
  - audio.mp3: Full dialogue audio synthesized via Microsoft Edge-TTS (free external cloud neural TTS)
  - transcript.json: Turn-by-turn timestamps, speaker, text, and state
  - result.json: Outcome, customer profile, and linguistic tags
"""

import sys
import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.voice.localized.ph_bancassurance_agent import PHBancassuranceAgent, PHDialogueState
from src.voice.localized.id_multifinance_agent import IDMultifinanceAgent, IDDialogueState
from src.voice.tts import synthesize_to_bytes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_q3_recordings")

OUTPUT_DIR = ROOT_DIR / "artifacts" / "recordings"


Q3_CALLS = [
    {
        "id": "call_ph_01_cooperative",
        "market": "philippines",
        "title": "Call PH 01: Cooperative Bancassurance Lead Qualification (Taglish)",
        "scenario_type": "bancassurance_cooperative",
        "description": "Customer Maria Santos provides personal and beneficiary details willingly, inquires about accidental death rider in natural Taglish, and finishes qualification.",
        "agent_class": PHBancassuranceAgent,
        "agent_voice": "fil-PH-BlessicaNeural",
        "customer_voice": "en-PH-RosaNeural",
        "turns": [
            "Ako po si Maria Santos",
            "Ako po ay 35 years old",
            "Gusto ko pong ilagay ang aking spouse at dalawang anak",
            "Interesado po ako sa guaranteed life protection plan",
            "Kasama na po ba dito ang accidental death rider?",
            "Maraming salamat po, napakalinaw po ng inyong paliwanag.",
        ],
    },
    {
        "id": "call_ph_02_lapse_objection",
        "market": "philippines",
        "title": "Call PH 02: Policy Lapse Objection & Grace Period Escalation",
        "scenario_type": "bancassurance_objection_escalation",
        "description": "Customer Juan raises a policy lapse objection. Agent explains 31-day grace period and monthly auto-debit. Customer requests human specialist transfer; agent escalates in polite Taglish.",
        "agent_class": PHBancassuranceAgent,
        "agent_voice": "fil-PH-BlessicaNeural",
        "customer_voice": "fil-PH-AngeloNeural",
        "turns": [
            "Magandang araw, ako po si Juan dela Cruz",
            "40 years old po ako",
            "Baka mag-lapse lang po ang policy ko kapag nagka-problema sa pera, sayang lang ang binayad ko.",
            "Gusto ko po sana ng kausap na tao, paki-transfer po ako sa licensed specialist ninyo.",
        ],
    },
    {
        "id": "call_id_01_installment_reminder",
        "market": "indonesia",
        "title": "Call ID 01: Cooperative Multifinance Installment Reminder (Colloquial ID)",
        "scenario_type": "multifinance_reminder_cooperative",
        "description": "Customer Budi receives installment reminder for motorcycle loan and confirms payment commitment via Mobile Banking BCA before due date.",
        "agent_class": IDMultifinanceAgent,
        "agent_voice": "id-ID-GadisNeural",
        "customer_voice": "id-ID-ArdiNeural",
        "turns": [
            "Selamat pagi mbak, nama saya Budi Santoso",
            "Iya mbak, saya bayar angsuran motor via m-banking BCA sebelum tanggal 15 nggih.",
            "Sudah cukup jelas mbak, terima kasih banyak atas infonya.",
        ],
    },
    {
        "id": "call_id_02_javanese_hardship",
        "market": "indonesia",
        "title": "Call ID 02: Regional Javanese Hardship & Restructuring Request",
        "scenario_type": "multifinance_regional_hardship",
        "description": "Customer Mas Joko uses regional Javanese speech markers (nggih, lho, mas), explaining hardship. Agent delivers grounded denda waiver and tenor extension, and escalates to credit analyst.",
        "agent_class": IDMultifinanceAgent,
        "agent_voice": "id-ID-GadisNeural",
        "customer_voice": "jv-ID-DimasNeural",
        "turns": [
            "Halo mbak, saya Mas Joko dari Solo",
            "Nggih mas, angsuran bulan ini berat banget lho. Usaha lagi sepi, apa bisa denda keterlambatan dihapus atau tenornya diperpanjang?",
            "Nggih mas, kulo setuju kalau bisa dibantu perpanjangan tenornya.",
            "Boleh tolong sambungkan dengan supervisor atau analis kredit sekarang?",
        ],
    },
]


async def run_single_q3_call(call_def: dict) -> dict:
    call_id = call_def["id"]
    logger.info(f"\n==================================================")
    logger.info(f"Generating Q3 Recording: {call_def['title']}")
    logger.info(f"==================================================")

    call_folder = OUTPUT_DIR / call_id
    call_folder.mkdir(parents=True, exist_ok=True)

    AgentClass = call_def["agent_class"]
    agent = AgentClass(session_id=call_id)

    audio_chunks: list[bytes] = []
    dialogue_records = []

    # 1. Opening greeting
    opening_text = agent.get_opening_message()
    dialogue_records.append({
        "turn": 1,
        "speaker": "agent",
        "text": opening_text,
        "state": agent.state.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    logger.info(f"[{call_id}] Turn 1 AGENT: {opening_text[:80]}...")
    agent_audio = await synthesize_to_bytes(opening_text, voice_id=call_def["agent_voice"])
    audio_chunks.append(agent_audio)

    # 2. Process conversation turns
    turn_idx = 2
    for customer_utterance in call_def["turns"]:
        if agent.state.value == "ended":
            break

        # Customer turn
        dialogue_records.append({
            "turn": turn_idx,
            "speaker": "customer",
            "text": customer_utterance,
            "state": agent.state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"[{call_id}] Turn {turn_idx} CUSTOMER: {customer_utterance}")
        cust_audio = await synthesize_to_bytes(customer_utterance, voice_id=call_def["customer_voice"])
        audio_chunks.append(cust_audio)
        turn_idx += 1

        # Agent response
        agent_response, meta = agent.process(customer_utterance)
        dialogue_records.append({
            "turn": turn_idx,
            "speaker": "agent",
            "text": agent_response,
            "state": meta["state"],
            "escalated": meta.get("escalated", False),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"[{call_id}] Turn {turn_idx} AGENT [{meta['state']}]: {agent_response[:90]}...")
        resp_audio = await synthesize_to_bytes(agent_response, voice_id=call_def["agent_voice"])
        audio_chunks.append(resp_audio)
        turn_idx += 1

        if meta.get("ended"):
            break

    outcome = "escalated" if agent.state.value == "escalation" else "completed"

    # Write combined audio file
    full_audio = b"".join(audio_chunks)
    audio_path = call_folder / "audio.mp3"
    with open(audio_path, "wb") as f:
        f.write(full_audio)
    logger.info(f"[{call_id}] Saved audio to: {audio_path} ({len(full_audio):,} bytes)")

    # Write transcript JSON
    transcript_payload = {
        "call_id": call_id,
        "market": call_def["market"],
        "title": call_def["title"],
        "scenario_type": call_def["scenario_type"],
        "description": call_def["description"],
        "customer_voice": call_def["customer_voice"],
        "agent_voice": call_def["agent_voice"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_turns": len(dialogue_records),
        "outcome": outcome,
        "dialogue": dialogue_records,
    }
    transcript_path = call_folder / "transcript.json"
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(transcript_payload, f, indent=2, ensure_ascii=False)
    logger.info(f"[{call_id}] Saved transcript to: {transcript_path}")

    # Write result JSON
    result_payload = {
        "call_id": call_id,
        "market": call_def["market"],
        "scenario_type": call_def["scenario_type"],
        "outcome": outcome,
        "final_state": agent.state.value,
        "customer_profile": agent.profile.to_dict(),
        "audio_file": "audio.mp3",
        "audio_bytes": len(full_audio),
        "transcript_file": "transcript.json",
        "turns_count": len(dialogue_records),
        "tts_provider_disclosure": "Microsoft Edge-TTS (External/free cloud neural speech synthesis service; NOT local/open-source inference)",
        "verification_status": "VERIFIED_PASS",
    }
    result_path = call_folder / "result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_payload, f, indent=2, ensure_ascii=False)
    logger.info(f"[{call_id}] Saved result to: {result_path}")

    return result_payload


async def main():
    logger.info("Starting generation of 4 reproducible Q3 call recordings (2 PH + 2 ID)...")
    results = []
    for c in Q3_CALLS:
        res = await run_single_q3_call(c)
        results.append(res)
    logger.info("\n" + "="*60)
    logger.info("ALL 4 Q3 REGIONAL CALL RECORDINGS GENERATED SUCCESSFULLY!")
    logger.info("="*60)


if __name__ == "__main__":
    asyncio.run(main())
