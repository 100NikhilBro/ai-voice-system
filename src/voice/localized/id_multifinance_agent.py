"""
Indonesia Multifinance Consumer Credit Voice Agent
==================================================
Implements formal & colloquial Bahasa Indonesia dialogue with financial loanwords
and regional Javanese speech awareness for multifinance installment reminders,
restructuring, and objection handling.

Linguistic Features:
- Consumer finance terms: cicilan, tenor, denda, DP, jatuh tempo, angsuran, pembiayaan
- Regional speech markers: nggih, monggo, lho, mas, mbak, Pak, Bu
- Crucial distinction: treats 'nggih' (/ŋɡiʔ/) as affirmative agreement,
  preventing acoustic confusion with negative 'nggak' (/ŋɡaʔ/)
- Fallback & escalation strictly preserve the respectful Indonesian customer register.
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

ID_DOMAIN_DIR = Path(__file__).resolve().parent.parent.parent.parent / "domains" / "indonesia_multifinance" / "raw_docs"


class IDDialogueState(str, Enum):
    GREETING               = "greeting"
    INSTALLMENT_REMINDER   = "installment_reminder"
    OBJECTION_HANDLING     = "objection_handling"
    RESTRUCTURING_PROPOSAL = "restructuring_proposal"
    CONFIRMATION           = "confirmation"
    ESCALATION             = "escalation"
    ENDED                  = "ended"


@dataclass
class IDCustomerProfile:
    name: Optional[str]              = None
    contract_number: Optional[str]   = None
    installment_amount_idr: int      = 850000
    due_date_day: int                = 15
    hardship_reason: Optional[str]   = None
    restructuring_requested: bool    = False
    payment_commitment_date: Optional[str] = None
    flags: List[str]                 = field(default_factory=list)
    regional_dialect_markers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "contract_number": self.contract_number,
            "installment_amount_idr": self.installment_amount_idr,
            "due_date_day": self.due_date_day,
            "hardship_reason": self.hardship_reason,
            "restructuring_requested": self.restructuring_requested,
            "payment_commitment_date": self.payment_commitment_date,
            "flags": self.flags,
            "regional_dialect_markers": self.regional_dialect_markers,
        }


def _extract_name_id(text: str) -> Optional[str]:
    patterns = [
        r"(?:nama saya|saya|dengan)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)$",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip().title()
    return None


def _is_indonesian_affirmative(text: str) -> bool:
    """
    Detect affirmative intent. Specifically includes Javanese affirmative 'nggih' / 'inggih'
    and formal/colloquial Indonesian 'iya', 'bisa', 'siap', 'oke'.
    """
    return bool(re.search(r"\b(nggih|inggih|iya|ya|betul|benar|bisa|siap|oke|ok|setuju|monggo)\b", text, re.IGNORECASE))


def _is_indonesian_negative(text: str) -> bool:
    """
    Detect negative intent. Strictly checks 'tidak', 'nggak', 'gak', 'bukan', 'belum'.
    Note: 'nggih' must NOT match here!
    """
    # Remove 'nggih' explicitly to avoid false negative match
    sanitized = re.sub(r"\bnggih\b", "", text, flags=re.IGNORECASE)
    return bool(re.search(r"\b(tidak|nggak|gak|bukan|belum|jangan|ndak|ora)\b", sanitized, re.IGNORECASE))


def _detect_javanese_markers(text: str) -> List[str]:
    """Detect regional Javanese dialect and discourse markers."""
    detected = []
    markers = [
        ("nggih", "javanese_affirmative_nggih"),
        ("monggo", "javanese_polite_monggo"),
        ("lho", "javanese_emphasis_lho"),
        ("mas", "address_mas"),
        ("mbak", "address_mbak"),
        ("jenengan", "javanese_pronoun_jenengan"),
        ("dolan", "javanese_lexical"),
    ]
    for word, tag in markers:
        if re.search(rf"\b{word}\b", text, re.IGNORECASE):
            detected.append(tag)
    return detected


def _wants_id_escalation(text: str) -> bool:
    return bool(re.search(
        r"\b(supervisor|analis kredit|petugas manusia|orang|kepala cabang|manajer|bicara langsung|sambungkan)\b",
        text, re.IGNORECASE
    ))


def _is_id_objection(text: str) -> bool:
    return bool(re.search(
        r"\b(berat|telat|mundur|sepi|denda|keringanan|potongan|nggak ada uang|belum ada|tenor|perpanjang|sulit|angsuran.*berat)\b",
        text, re.IGNORECASE
    ))


class IDMultifinanceAgent:
    """
    Stateful conversational agent for Indonesia Multifinance (Consumer Credit).
    Handles formal & colloquial Indonesian, finance loanwords, and Javanese regional speech.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.state = IDDialogueState.GREETING
        self.profile = IDCustomerProfile()
        self.turn_count = 0
        self._awaiting: Optional[str] = None
        self._load_knowledge()

    def _load_knowledge(self):
        try:
            faq_path = ID_DOMAIN_DIR / "multifinance_faqs_objections.md"
            self.faq_text = faq_path.read_text(encoding="utf-8") if faq_path.exists() else ""
            prod_path = ID_DOMAIN_DIR / "multifinance_products.md"
            self.prod_text = prod_path.read_text(encoding="utf-8") if prod_path.exists() else ""
        except Exception as e:
            logger.warning(f"[IDAgent] Knowledge load error: {e}")
            self.faq_text = ""
            self.prod_text = ""

    def get_opening_message(self) -> str:
        return (
            "Selamat pagi Bapak/Ibu, salam dari HealthShield Multifinance. "
            "Saya Gadis, asisten layanan pelanggan resmi Anda. "
            "Panggilan ini terhubung untuk konfirmasi jadwal angsuran pembiayaan motor Anda. "
            "Boleh dibantu konfirmasi atas nama siapa saya berbicara saat ini?"
        )

    def process(self, utterance: str) -> Tuple[str, Dict[str, Any]]:
        self.turn_count += 1
        utterance = utterance.strip()

        # Track regional linguistic markers in customer speech
        markers = _detect_javanese_markers(utterance)
        for m in markers:
            if m not in self.profile.regional_dialect_markers:
                self.profile.regional_dialect_markers.append(m)

        # Global escalation check (Polite Indonesian preserved)
        if _wants_id_escalation(utterance) and self.state not in (
            IDDialogueState.ESCALATION, IDDialogueState.ENDED
        ):
            return self._escalate("Customer requested credit analyst / human supervisor.")

        if self.state == IDDialogueState.GREETING:
            response = self._handle_greeting(utterance)
        elif self.state == IDDialogueState.INSTALLMENT_REMINDER:
            response = self._handle_installment_reminder(utterance)
        elif self.state in (IDDialogueState.OBJECTION_HANDLING, IDDialogueState.RESTRUCTURING_PROPOSAL):
            response = self._handle_objection_and_restructuring(utterance)
        elif self.state == IDDialogueState.CONFIRMATION:
            response = self._handle_confirmation(utterance)
        elif self.state == IDDialogueState.ESCALATION:
            response = self._handle_escalation(utterance)
        else:
            response = "Terima kasih banyak atas waktu dan kerja sama Bapak/Ibu bersama HealthShield Multifinance. Selamat beraktivitas!"

        meta = {
            "state": self.state.value,
            "turn": self.turn_count,
            "market": "indonesia",
            "language_mode": "bahasa_indonesia",
            "regional_markers": self.profile.regional_dialect_markers,
            "qualification_profile": self.profile.to_dict(),
            "ended": self.state == IDDialogueState.ENDED,
            "escalated": self.state == IDDialogueState.ESCALATION,
        }
        return response, meta

    def _handle_greeting(self, utterance: str) -> str:
        name = _extract_name_id(utterance)
        if name:
            self.profile.name = name
        self.state = IDDialogueState.INSTALLMENT_REMINDER
        name_str = f" {self.profile.name}" if self.profile.name else ""

        # Acknowledge regional tone warmly if detected
        regional_greet = "nggih " if "javanese_affirmative_nggih" in self.profile.regional_dialect_markers else ""

        return (
            f"Terima kasih atas konfirmasinya Pak/Bu{name_str}. {regional_greet.capitalize()}"
            "Kami ingin menginformasikan bahwa angsuran sepeda motor Anda sebesar Rp 850.000 "
            "akan jatuh tempo dalam 2 hari ke depan pada tanggal 15. "
            "Apakah pembayaran rencana akan dilakukan melalui Mobile Banking atau kasir Indomaret/Alfamart?"
        )

    def _handle_installment_reminder(self, utterance: str) -> str:
        # Check customer objection or hardship
        if _is_id_objection(utterance):
            return self._handle_objection_response(utterance)

        # Customer confirms payment channel
        if any(w in utterance.lower() for w in ["m-banking", "mobile banking", "bca", "mandiri", "bri", "atm", "transfer"]):
            self.profile.payment_commitment_date = "tanggal 15 via m-banking"
            self.state = IDDialogueState.CONFIRMATION
            return (
                "Baik, luar biasa sekali. Pembayaran via transfer Virtual Account m-banking "
                "akan otomatis terverifikasi secara real-time tanpa potongan biaya admin tambahan. "
                "Apakah ada yang perlu kami bantu kembali terkait nomor kontrak atau rincian angsuran Anda?"
            )

        if any(w in utterance.lower() for w in ["indomaret", "alfamart", "kasir", "minimarket"]):
            self.profile.payment_commitment_date = "tanggal 15 via Indomaret/Alfamart"
            self.state = IDDialogueState.CONFIRMATION
            return (
                "Baik, sangat praktis. Di kasir Indomaret atau Alfamart cukup sebutkan pembayaran HealthShield Multifinance "
                "dan tunjukkan nomor kontrak pembiayaan Anda. "
                "Ada hal lain yang ingin ditanyakan sebelum kami tutup laporannya?"
            )

        # Customer agrees with affirmative (including Javanese 'nggih')
        if _is_indonesian_affirmative(utterance):
            self.profile.payment_commitment_date = "tepat waktu sebelum jatuh tempo"
            self.state = IDDialogueState.CONFIRMATION
            return (
                "Baik, terima kasih atas komitmen pembayarannya nggih Pak/Bu. "
                "Pembayaran sebelum tanggal jatuh tempo menjaga skor kredit Anda tetap aman dan terhindar dari denda keterlambatan. "
                "Apakah ada pertanyaan lain seputar pembiayaan motor Anda?"
            )

        return (
            "Mohon maaf, kami kurang menangkap tanggapan Anda. "
            "Apakah pembayaran angsuran motor Anda bisa dibantu konfirmasi pembayarannya sebelum jatuh tempo tanggal 15?"
        )

    def _handle_objection_and_restructuring(self, utterance: str) -> str:
        utt_lower = utterance.lower()

        # Closing signal
        if _is_indonesian_affirmative(utterance) and any(w in utt_lower for w in ["terima kasih", "makasih", "cukup", "jelas", "paham"]):
            return self._conclude_call()

        if any(w in utt_lower for w in ["terima kasih", "makasih", "matur nuwun", "cukup", "sudah jelas"]):
            return self._conclude_call()

        # Follow-up on restructuring acceptance
        if _is_indonesian_affirmative(utterance) and self.state == IDDialogueState.RESTRUCTURING_PROPOSAL:
            self.profile.flags.append("restructuring_lead_created")
            self.state = IDDialogueState.CONFIRMATION
            return (
                "Baik nggih Mas/Pak. Saya sudah catatkan pengajuan perpanjangan tenor pembiayaan Anda. "
                "Tim analis kredit kami akan menghubungi Anda kembali dalam 1x24 jam untuk simulasi angsuran yang lebih ringan. "
                "Apakah ada pertanyaan lain sebelum kami akhiri panggilan ini?"
            )

        # Grounded lookup on late fees
        if "denda" in utt_lower or "potongan" in utt_lower:
            return (
                "Sesuai pedoman resmi, denda keterlambatan kami adalah 0.5% per hari setelah masa tenggang 3 hari. "
                "Namun bagi nasabah yang melunasi pokok angsuran dalam 24 jam ke depan, kami bisa bantu ajukan penghapusan denda (denda waiver) hingga 100%. "
                "Apakah Bapak/Ibu bersedia melunasi pokoknya besok agar dendanya kami bantu hapuskan?"
            )

        # Grounded lookup on tenor
        if "tenor" in utt_lower or "perpanjang" in utt_lower:
            return (
                "Untuk fasilitas perpanjangan tenor restrukturisasi, tersedia tambahan waktu 6 hingga 12 bulan "
                "agar nilai cicilan bulanan Anda bisa turun signifikan. "
                "Boleh kami bantu buatkan laporan pengajuannya sekarang?"
            )

        return (
            "Kami sangat memahami situasi Bapak/Ibu. Apabila ada kendala pembayaran, "
            "tim kami siap memberikan solusi terbaik agar terhindar dari denda dan catatan kredit tetap terjaga baik. "
            "Apakah ada hal lain yang bisa kami bantu?"
        )

    def _handle_objection_response(self, utterance: str) -> str:
        self.state = IDDialogueState.OBJECTION_HANDLING
        utt_lower = utterance.lower()

        # Check regional speech / hardship
        if any(w in utt_lower for w in ["berat", "sepi", "gaji", "mundur", "belum ada", "nunggak"]):
            self.profile.hardship_reason = utterance[:80]
            self.profile.restructuring_requested = True
            self.state = IDDialogueState.RESTRUCTURING_PROPOSAL

            regional_marker = "Nggih Mas/Pak, " if "javanese_affirmative_nggih" in self.profile.regional_dialect_markers else "Baik Pak/Bu, "

            return (
                f"{regional_marker}kami sangat mengerti dan berempati dengan kendala yang dihadapi saat ini. "
                "Khusus untuk nasabah setia, kami memiliki solusi restrukturisasi perpanjangan tenor hingga 12 bulan ke depan "
                "agar nilai cicilan per bulannya bisa jauh lebih enteng, serta program keringanan denda keterlambatan. "
                "Apakah berkenan kami bantu ajukan program perpanjangan tenor ini untuk cicilan Anda?"
            )

        if "denda" in utt_lower:
            return (
                "Kami mengerti keberatan Anda mengenai denda. "
                "Jika pembayaran pokok dilakukan sebelum akhir pekan ini, kami dapat mengajukan fasilitas penghapusan denda keterlambatan (denda waiver). "
                "Apakah Bapak/Ibu bisa berkomitmen untuk pembayaran pokok tersebut?"
            )

        return (
            "Kami sangat menghargai keterbukaan Anda. Di HealthShield Multifinance, kami selalu mengutamakan solusi kekeluargaan "
            "bagi nasabah yang mengalami kendala cicilan. Apakah Anda ingin kami bantu sambungkan dengan analis kredit kami?"
        )

    def _handle_confirmation(self, utterance: str) -> str:
        self.state = IDDialogueState.ENDED
        return (
            "Terima kasih banyak atas waktu dan komitmennya nggih Bapak/Ibu. "
            "Informasi telah tercatat lengkap dalam sistem kami. "
            "Selamat pagi/siang dan semoga sehat selalu bersama keluarga!"
        )

    def _conclude_call(self) -> str:
        self.state = IDDialogueState.ENDED
        return (
            "Sama-sama nggih Bapak/Ibu! Terima kasih telah menjadi nasabah setia HealthShield Multifinance. "
            "Semoga rezeki lancar selalu. Selamat beraktivitas!"
        )

    def _handle_escalation(self, utterance: str) -> str:
        self.state = IDDialogueState.ENDED
        return (
            "Baik, saya segera menyambungkan telepon ini kepada petugas supervisor dan analis pembiayaan resmi kami. "
            "Mohon ditunggu di sambungan telepon nggih Pak/Bu. Terima kasih."
        )

    def _escalate(self, reason: str) -> Tuple[str, Dict[str, Any]]:
        self.state = IDDialogueState.ESCALATION
        response = (
            "Baik, saya sangat memahami kebutuhan Bapak/Ibu. Segera saya sambungkan dengan analis kredit dan supervisor resmi kami "
            "untuk membantu solusi pembiayaan Anda secara tuntas. Mohon ditunggu sebentar nggih Pak/Bu."
        )
        meta = {
            "state": self.state.value,
            "turn": self.turn_count,
            "market": "indonesia",
            "language_mode": "bahasa_indonesia",
            "regional_markers": self.profile.regional_dialect_markers,
            "qualification_profile": self.profile.to_dict(),
            "ended": False,
            "escalated": True,
            "escalation_reason": reason,
        }
        return response, meta
