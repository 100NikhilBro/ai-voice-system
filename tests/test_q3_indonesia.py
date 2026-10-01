"""
Q3 Indonesia Multifinance Voice Agent Tests
===========================================
Verifies:
1. Cooperative installment reminder (angsuran jatuh tempo) via m-banking/Indomaret
2. Javanese regional speech handling (nggih, monggo, lho, mas) and hardship restructuring
3. Late fee (denda) waiver and tenor extension grounded responses
4. In-register polite Indonesian human escalation
5. Linguistic disambiguation: affirmative 'nggih' vs negative 'nggak'
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

from src.voice.localized.id_multifinance_agent import (
    IDMultifinanceAgent,
    IDDialogueState,
    _is_indonesian_affirmative,
    _is_indonesian_negative,
    _detect_javanese_markers,
)

logger = logging.getLogger(__name__)


def test_id_cooperative_installment_reminder():
    """
    Scenario 1: Cooperative customer Budi Santoso receives installment reminder
    and confirms payment via Mobile Banking before due date.
    """
    agent = IDMultifinanceAgent("test-id-coop-01")
    opening = agent.get_opening_message()
    assert "HealthShield Multifinance" in opening
    assert "angsuran" in opening.lower()

    # Step 1: Greeting
    resp1, meta1 = agent.process("Selamat pagi, nama saya Budi Santoso")
    assert agent.profile.name == "Budi Santoso"
    assert "850.000" in resp1
    assert "jatuh tempo" in resp1.lower()

    # Step 2: Payment channel confirmation
    resp2, meta2 = agent.process("Iya mbak, saya bayar via m-banking BCA sebelum tanggal 15")
    assert meta2["state"] == IDDialogueState.CONFIRMATION.value
    assert agent.profile.payment_commitment_date is not None
    assert "virtual account" in resp2.lower()

    # Step 3: Conclude
    resp3, meta3 = agent.process("Sudah cukup jelas, terima kasih banyak mbak")
    assert meta3["state"] == IDDialogueState.ENDED.value
    assert any(w in resp3.lower() for w in ["sama-sama", "terima kasih", "nasabah setia"])

    logger.info("[PASS] test_id_cooperative_installment_reminder verified.")


def test_id_javanese_hardship_and_restructuring():
    """
    Scenario 2: Customer speaks with Javanese regional dialect markers (nggih, monggo, lho, mas),
    explaining hardship (usaha sepi / gaji telat). Agent delivers grounded objection response
    (denda waiver + tenor extension), customer agrees, and escalates for analyst signoff.
    """
    agent = IDMultifinanceAgent("test-id-javanese-02")
    agent.get_opening_message()

    # Step 1: Greeting with regional address
    resp1, _ = agent.process("Halo mbak, saya Mas Joko dari Solo")
    assert "Joko" in (agent.profile.name or "")
    assert "address_mas" in agent.profile.regional_dialect_markers

    # Step 2: Javanese hardship objection
    hardship_utterance = (
        "Nggih mas, angsuran bulan ini berat banget lho. "
        "Usaha lagi sepi, apa bisa denda keterlambatan dihapus atau tenornya diperpanjang?"
    )
    resp2, meta2 = agent.process(hardship_utterance)

    # Verify regional markers captured
    assert "javanese_affirmative_nggih" in agent.profile.regional_dialect_markers
    assert "javanese_emphasis_lho" in agent.profile.regional_dialect_markers
    assert agent.profile.restructuring_requested is True

    # Grounded response verification: agent should acknowledge in empathetic regional tone
    # and mention tenor restructuring up to 12 months & denda waiver
    assert "nggih" in resp2.lower() or "mas" in resp2.lower() or "pak" in resp2.lower()
    assert any(term in resp2.lower() for term in ["tenor", "restrukturisasi", "denda", "12 bulan"])

    # Step 3: Acceptance of restructuring
    resp3, meta3 = agent.process("Nggih mas, kulo setuju kalau bisa dibantu perpanjangan tenornya.")
    assert "restructuring_lead_created" in agent.profile.flags
    assert "analis kredit" in resp3.lower() or "simulasi" in resp3.lower()

    # Step 4: Human escalation
    resp4, meta4 = agent.process("Boleh tolong sambungkan dengan supervisor atau analis kredit sekarang?")
    assert meta4["state"] == IDDialogueState.ESCALATION.value
    assert meta4["escalated"] is True
    # Escalation remains in polite Indonesian register (does not revert to cold English)
    assert any(w in resp4.lower() for w in ["nggih", "pak/bu", "analis kredit", "supervisor", "sambungkan"])

    logger.info("[PASS] test_id_javanese_hardship_and_restructuring verified.")


def test_id_nggih_affirmative_vs_nggak_negative():
    """
    Scenario 3: Linguistic Ambiguity Test.
    Ensures that Javanese affirmative 'nggih' (/ŋɡiʔ/) is recognized as affirmative,
    and NEVER falsely triggered as Indonesian negative 'nggak' (/ŋɡaʔ/).
    """
    # Affirmative tests
    affirmative_samples = [
        "Nggih mas, saya bayar besok",
        "Nggih, setuju sekali",
        "Inggih Pak, siap",
        "Iya, bisa lewat Indomaret",
    ]
    for s in affirmative_samples:
        assert _is_indonesian_affirmative(s) is True, f"Failed affirmative for: {s}"
        assert _is_indonesian_negative(s) is False, f"False negative triggered for: {s}"

    # Negative tests
    negative_samples = [
        "Nggak bisa bayar sekarang",
        "Belum ada dananya mas",
        "Gak mau kalau ada denda",
        "Tidak setuju",
    ]
    for s in negative_samples:
        assert _is_indonesian_negative(s) is True, f"Failed negative for: {s}"

    # Regional marker detector test
    markers = _detect_javanese_markers("Nggih monggo mas, lho kok belum selesai?")
    assert "javanese_affirmative_nggih" in markers
    assert "javanese_polite_monggo" in markers
    assert "javanese_emphasis_lho" in markers
    assert "address_mas" in markers

    logger.info("[PASS] test_id_nggih_affirmative_vs_nggak_negative verified.")


if __name__ == "__main__":
    test_id_cooperative_installment_reminder()
    test_id_javanese_hardship_and_restructuring()
    test_id_nggih_affirmative_vs_nggak_negative()
    print("ALL INDONESIA Q3 TESTS PASSED!")
