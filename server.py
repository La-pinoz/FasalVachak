# server.py

import asyncio
from livekit import rtc
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.plugins import deepgram  # Or your chosen STT provider

# Import your custom modules
from dialogue.session import DialogueManager
from tts.rime_client import play_audio  # Your Rime TTS wrapper


async def entrypoint(ctx: JobContext):
    """Bootstraps the agent when a farmer joins the Twilio/LiveKit room."""
    await ctx.connect()
    print("Agent joined the room.")

    # 1. Initialize per-call session state
    session = DialogueManager()

    # 2. Phase 0: Play fixed greeting immediately (No LLM)
    greeting = "Namaste, KrishiSeva mein aapka swagat hai. Aapki dhaan ya kapas ki fasal mein kya lakshan dikh rahe hain, kripya bataiye?"
    await play_audio(ctx.room, greeting)

    # 3. Set up the STT Client
    stt_client = deepgram.STT()

    # 4. Listen for the farmer's audio track
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            print("Audio track subscribed, starting STT stream...")
            # Run the STT processing loop in the background
            asyncio.create_task(handle_stt_stream(
                track, ctx.room, stt_client, session))


async def handle_stt_stream(track: rtc.Track, room: rtc.Room, stt_client, session: DialogueManager):
    """Captures audio frames, sends to STT, and routes text to the dialogue manager."""
    stt_stream = stt_client.stream()

    # Push audio from the LiveKit track into the STT stream
    asyncio.create_task(stt_stream.push_track(track))

    # Listen to the STT events coming back
    async for event in stt_stream:
        # We only want to act when the VAD/STT decides the user is done speaking
        if event.type == "transcript" and event.is_final:
            farmer_text = event.alternatives[0].text.strip()

            if not farmer_text:
                continue

            print(f"Farmer said: {farmer_text}")

            # 5. Route STT text to the Dialogue Manager
            # The manager updates its internal state and returns the next text to speak
            next_agent_response = await session.process_turn(farmer_text)

            # 6. Play the resulting audio (ASK question, ANSWER diagnosis, or fallback)
            if next_agent_response:
                await play_audio(room, next_agent_response)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
