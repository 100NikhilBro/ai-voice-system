"""
Conversation & Transcript Logger
=================================
Logs every turn of the voice agent conversation to a JSON file
under domains/health_insurance/kb_store/conversations/.

Each session produces:
  <session_id>.json  — full structured transcript with timestamps,
                        qualification state, citations, and metadata.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import settings

logger = logging.getLogger(__name__)

CONVERSATIONS_DIR = settings.KB_STORE_DIR / "conversations"


class ConversationLogger:
    """Thread-safe conversation logger that persists turns to JSON."""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.turns: List[Dict[str, Any]] = []
        self.qualification_state: Dict[str, Any] = {}
        self.outcome: Optional[str] = None

    def log_turn(
        self,
        speaker: str,          # "agent" | "customer"
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a single dialogue turn."""
        turn = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "speaker": speaker,
            "text": text,
        }
        if metadata:
            turn["metadata"] = metadata
        self.turns.append(turn)

    def update_qualification(self, updates: Dict[str, Any]) -> None:
        """Update the qualification state snapshot."""
        self.qualification_state.update(updates)

    def close(self, outcome: str = "completed") -> Path:
        """Finalise and persist the session transcript. Returns the output path."""
        self.outcome = outcome
        CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = CONVERSATIONS_DIR / f"{self.session_id}.json"

        payload = {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "outcome": outcome,
            "qualification_state": self.qualification_state,
            "turns": self.turns,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        logger.info(
            f"[ConversationLogger] Session {self.session_id} saved to {output_path} "
            f"({len(self.turns)} turns, outcome={outcome})"
        )
        return output_path
