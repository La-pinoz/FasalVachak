# server.py
"""
LiveKit voice agent entrypoint for FasalVachak (livekit-agents v1.8 compatible).

Pipeline:
  Farmer (phone/browser) → LiveKit room → Deepgram STT
  → DialogueManager (Groq LLM + KB) → Deepgram TTS → LiveKit room → Farmer
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

from livekit import rtc
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents import stt as agents_stt
from livekit.plugins import deepgram, rime

from dialogue.session import DialogueManager
from tts.rime_tts import create_tts_client, play_audio


def safe_print(msg: str) -> None:
    """Print that works even when the Windows console doesn't support Unicode."""
    try:
        print(msg)
    except UnicodeEncodeError:
        # Encode to UTF-8 and write directly to the binary stdout buffer
        sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()


async def entrypoint(ctx: JobContext) -> None:
    """Bootstraps the agent when a farmer joins the LiveKit room."""
    await ctx.connect()
    safe_print("[Server] Agent connected to room.")

    # ── Fresh TTS client + HTTP session per job ─────────────────────────────
    tts_client, tts_session = create_tts_client()

    # ── Per-call dialogue state ─────────────────────────────────────────────
    session = DialogueManager()

    # ── STT client ──────────────────────────────────────────────────────────
    stt_client = deepgram.STT(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        language="hi",
        model="nova-2",
        interim_results=False,
        smart_format=True,
    )

    # ── Event to keep the job alive until the room disconnects ──────────────
    disconnected_event = asyncio.Event()

    @ctx.room.on("disconnected")
    def on_disconnected(*_args) -> None:
        disconnected_event.set()

    # ── Helper: start STT for a REMOTE participant's audio track only ────────
    def start_stt_for_track(track: rtc.Track, participant: rtc.RemoteParticipant) -> None:
        safe_print(f"[Server] Audio track from '{participant.identity}' — starting STT …")
        asyncio.create_task(
            handle_stt_stream(track, ctx.room, stt_client, session, tts_client)
        )

    # ── Handle tracks that arrive AFTER we connect (remote only) ─────────────
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        # Only listen to REMOTE participants — ignore our own agent tracks
        if (
            track.kind == rtc.TrackKind.KIND_AUDIO
            and isinstance(participant, rtc.RemoteParticipant)
        ):
            start_stt_for_track(track, participant)

    # ── Handle tracks ALREADY in the room when we joined (remote only) ───────
    for participant in ctx.room.remote_participants.values():
        for publication in participant.track_publications.values():
            if (
                publication.track is not None
                and publication.track.kind == rtc.TrackKind.KIND_AUDIO
            ):
                start_stt_for_track(publication.track, participant)

    # ── Play greeting AFTER setting up all listeners ─────────────────────────
    greeting = (
        "Namaste, KrishiSeva mein aapka swagat hai. "
        "Aapki dhaan ya kapas ki fasal mein kya lakshan dikh rahe hain, "
        "kripya bataiye?"
    )
    await play_audio(ctx.room, greeting, tts_client)

    # ── Keep the job alive until the room disconnects ────────────────────────
    try:
        await disconnected_event.wait()
    finally:
        await tts_session.close()
        safe_print("[Server] Room disconnected — cleaned up.")


async def handle_stt_stream(
    track: rtc.Track,
    room: rtc.Room,
    stt_client: deepgram.STT,
    session: DialogueManager,
    tts_client: rime.TTS,
) -> None:
    """
    Reads AudioFrames from the farmer's LiveKit track, feeds them to Deepgram
    STT via push_frame(), and routes final transcripts to the DialogueManager.
    """
    stt_stream = stt_client.stream()

    # Task A: Read frames from LiveKit track → push into STT
    async def push_audio_frames() -> None:
        audio_stream = rtc.AudioStream(track)
        async for frame_event in audio_stream:
            stt_stream.push_frame(frame_event.frame)
        await stt_stream.aclose()

    asyncio.create_task(push_audio_frames())

    # Task B: Consume STT events → filter finals → dialogue → TTS
    async for stt_event in stt_stream:
        if stt_event.type != agents_stt.SpeechEventType.FINAL_TRANSCRIPT:
            continue
        if not stt_event.alternatives:
            continue

        farmer_text = stt_event.alternatives[0].text.strip()
        if not farmer_text:
            continue

        safe_print(f"[STT] Farmer: {farmer_text}")

        try:
            next_response = await session.process_turn(farmer_text)
        except Exception as exc:
            safe_print(f"[DialogueManager] Error: {exc}")
            continue

        if next_response:
            safe_print(f"[Agent] Responding …")
            await play_audio(room, next_response, tts_client)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
