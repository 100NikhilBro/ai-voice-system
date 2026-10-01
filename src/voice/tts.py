"""
Local Text-to-Speech Provider (Edge-TTS)
=========================================
Uses Microsoft Edge-TTS (free, no API key, no DLL dependencies).
Streams MP3 audio bytes back to the caller.

Voice selection:
  English  : en-US-AriaNeural  (warm, professional female)
  Filipino : fil-PH-BlessicaNeural
  Indonesian: id-ID-GadisNeural

Compromise documentation (per Assessment requirement Q3):
  Edge-TTS produces standard national prosody; authentic regional
  phonetic dialects (e.g. Javanese medok intonation) are not
  reproduced — this is an industry-wide limitation of commercial
  neural speech synthesis and is documented here explicitly.
"""

import asyncio
import io
import logging
from typing import AsyncIterator, Optional

import edge_tts

logger = logging.getLogger(__name__)

VOICE_MAP = {
    "en": "en-US-AriaNeural",
    "tl": "fil-PH-BlessicaNeural",
    "id": "id-ID-GadisNeural",
}

DEFAULT_VOICE = "en-US-AriaNeural"
DEFAULT_RATE = "+0%"
DEFAULT_VOLUME = "+0%"


async def synthesize_to_bytes(
    text: str,
    language: str = "en",
    voice_id: Optional[str] = None,
    rate: str = DEFAULT_RATE,
) -> bytes:
    """
    Synthesize *text* to MP3 bytes using Edge-TTS.

    Args:
        text: The text to speak.
        language: ISO 639-1 language code ('en', 'tl', 'id').
        voice_id: Override the default voice for this language.
        rate: Speech rate modifier (e.g. '+10%', '-5%').

    Returns:
        Raw MP3 audio bytes, ready to send to the browser.
    """
    voice = voice_id or VOICE_MAP.get(language, DEFAULT_VOICE)
    logger.info(f"[TTS] Synthesizing {len(text)} chars with voice={voice}")

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    audio_chunks: list[bytes] = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])

    audio_bytes = b"".join(audio_chunks)
    logger.info(f"[TTS] Generated {len(audio_bytes)} bytes of audio")
    return audio_bytes


async def synthesize_stream(
    text: str,
    language: str = "en",
    voice_id: Optional[str] = None,
) -> AsyncIterator[bytes]:
    """Async generator that yields MP3 chunks as they arrive."""
    voice = voice_id or VOICE_MAP.get(language, DEFAULT_VOICE)
    communicate = edge_tts.Communicate(text, voice)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]
