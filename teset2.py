# run_cli.py
"""
Terminal-based test harness for DialogueManager.
Lets you type farmer input as text and see the agent's responses,
without needing STT/TTS hooked up yet.

Usage:
    python run_cli.py
"""

import asyncio
import sys
import time

from dialogue.session import DialogueManager

DEBUG = True  # set to False to hide phase/latency info


def print_debug(dm: DialogueManager, turn_latency: float = None):
    if not DEBUG:
        return

    # State tracking output (Translation logs removed)
    print(f"    [debug] phase={dm.phase} | crop={dm.crop} | "
          f"questions_asked={dm.questions_asked} | followups_asked={dm.followups_asked}")

    if turn_latency is not None:
        print(f"    [debug] turn latency: {turn_latency:.2f}s")


async def main():
    dm = DialogueManager()
    call_start_time = time.monotonic()

    print("=" * 60)
    print("KrishiSeva Dialogue Test CLI")
    print("Type your response as the farmer (in Hindi/Hinglish). Type 'quit' or 'exit' to stop.")
    print("=" * 60)
    print()
    print("Agent: Namaste! Kripya bataiye, yeh dhaan ki samasya hai ya kapas ki, "
          "aur lakshan kya hain?")

    while True:
        try:
            farmer_input = input("\nFarmer: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nCall ended.")
            break

        if farmer_input.lower() in ("quit", "exit"):
            print("\nCall ended by user.")
            break

        if not farmer_input:
            print("Agent: Kripya kuch boliye.")
            continue

        try:
            # Measures the DialogueManager's processing time (LLM calls)
            turn_start = time.monotonic()

            # Text is now passed raw to the state machine, no translation step
            response = await dm.process_turn(farmer_input)

            turn_latency = time.monotonic() - turn_start
        except Exception as e:
            print(f"\n[ERROR] Something crashed: {e}")
            break

        print(f"\nAgent: {response}")
        print_debug(dm, turn_latency)

        if dm.phase == "completed":
            total_elapsed = time.monotonic() - call_start_time
            print(
                "\n--- Call has ended (phase=completed). Restart the script for a new call. ---")
            print(
                f"--- Total processing time this call: {total_elapsed:.2f}s ---")
            break


if __name__ == "__main__":
    if sys.platform == "win32":
        # Avoids occasional event loop issues on Windows terminals
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
