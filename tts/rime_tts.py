# tts/rime_tts.py
"""
Rime TTS wrapper for FasalVachak (livekit-agents v1.x compatible).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from livekit import rtc
from livekit.plugins import rime

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

_SAMPLE_RATE = 22050
_NUM_CHANNELS = 1


def create_tts_client() -> tuple[rime.TTS, aiohttp.ClientSession]:
    """
    Create a fresh Rime TTS client + its own aiohttp session.
    Call this once at the start of each job (inside entrypoint).
    """
    api_key = os.getenv("RIME_API_KEY")
    if not api_key or api_key == "your_rime_api_key_here":
        raise ValueError("\n\n>>> ❌ ERROR: RIME_API_KEY is missing! <<<\nYou MUST get a valid API key from https://app.rime.ai and replace 'your_rime_api_key_here' in your .env file.\n\n")

    session = aiohttp.ClientSession()
    tts = rime.TTS(
        api_key=os.getenv("RIME_API_KEY"),
        speaker="nadi",
        model="coda",
        lang="hin",
        sample_rate=_SAMPLE_RATE,
        http_session=session,
    )
    return tts, session


async def play_audio(source: rtc.AudioSource, text: str, tts: rime.TTS) -> None:
    """
    Synthesise *text* using Rime TTS and push audio frames to the persistent LiveKit track.

    Args:
        source: The persistent AudioSource connected to the room.
        text: The text to synthesise.
        tts:  The per-job TTS client (created via create_tts_client()).
    """
    if not text or not text.strip():
        return

    try:
        async with tts.synthesize(text) as tts_stream:
            async for synthesized in tts_stream:
                # capture_frame blocks and naturally paces the audio to realtime
                await source.capture_frame(synthesized.frame)
    except Exception as exc:
        print(f"[TTS] Synthesis error: {exc}")
