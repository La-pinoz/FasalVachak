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
    session = aiohttp.ClientSession()
    tts = rime.TTS(
        api_key=os.getenv("RIME_API_KEY"),
        model="mistv3",
        lang="hin",
        sample_rate=_SAMPLE_RATE,
        http_session=session,
    )
    return tts, session


async def play_audio(room: rtc.Room, text: str, tts: rime.TTS) -> None:
    """
    Synthesise *text* using Rime TTS and broadcast audio into the LiveKit room.
    Creates a LocalAudioTrack per utterance, pushes all TTS frames, unpublishes cleanly.

    Args:
        room: The LiveKit room to publish audio into.
        text: The text to synthesise.
        tts:  The per-job TTS client (created via create_tts_client()).
    """
    if not text or not text.strip():
        return

    source = rtc.AudioSource(sample_rate=_SAMPLE_RATE, num_channels=_NUM_CHANNELS)
    track = rtc.LocalAudioTrack.create_audio_track("agent-voice", source)
    pub_options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    publication = await room.local_participant.publish_track(track, pub_options)

    total_duration_s = 0.0
    try:
        async with tts.synthesize(text) as tts_stream:
            async for synthesized in tts_stream:
                frame = synthesized.frame
                # Accumulate audio duration so we can drain the buffer before unpublishing
                total_duration_s += frame.samples_per_channel / frame.sample_rate
                await source.capture_frame(frame)

        # Wait for the audio that is still in the LiveKit audio buffer to finish
        # playing before we tear down the track (prevents cutoff).
        if total_duration_s > 0:
            await asyncio.sleep(total_duration_s + 0.3)   # +300 ms safety margin

    except Exception as exc:
        print(f"[TTS] Synthesis error: {exc}")
    finally:
        await room.local_participant.unpublish_track(publication.sid)
