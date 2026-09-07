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
import time  # CHANGED: added for latency measurement

from dialogue.session import DialogueManager

DEBUG = True  # set to False to hide phase/translation info


# CHANGED: added turn_latency param
def print_debug(dm: DialogueManager, turn_latency: float = None):
    if not DEBUG:
        return
    print(f"    [debug] phase={dm.phase} | crop={dm.crop} | "
          f"questions_asked={dm.questions_asked} | followups_asked={dm.followups_asked}")
    if dm.translation_log:
        last_hindi, last_english = dm.translation_log[-1]
        print(f"    [debug] translated: '{last_hindi}' -> '{last_english}'")
    # CHANGED: new debug line — per-turn processing latency
    if turn_latency is not None:
        print(f"    [debug] turn latency: {turn_latency:.2f}s")


async def main():
    dm = DialogueManager()
    # CHANGED: marks start of the whole call, for cumulative timing
    call_start_time = time.monotonic()

    print("=" * 60)
    print("KrishiSeva Dialogue Test CLI")
    print("Type your response as the farmer. Type 'quit' or 'exit' to stop.")
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
            # CHANGED: wrapped process_turn with timing — this measures the
            # DialogueManager's own processing time (translation + LLM calls),
            # NOT real STT/TTS latency, since neither is hooked up yet.
            turn_start = time.monotonic()
            response = await dm.process_turn(farmer_input)
            turn_latency = time.monotonic() - turn_start
        except Exception as e:
            print(f"\n[ERROR] Something crashed: {e}")
            break

        print(f"\nAgent: {response}")
        print_debug(dm, turn_latency)  # CHANGED: pass turn_latency through

        if dm.phase == "completed":
            # CHANGED: report total call duration alongside the existing message
            total_elapsed = time.monotonic() - call_start_time
            print(
                "\n--- Call has ended (phase=completed). Restart the script for a new call. ---")
            # CHANGED: new line
            print(
                f"--- Total processing time this call: {total_elapsed:.2f}s ---")
            break


if __name__ == "__main__":
    if sys.platform == "win32":
        # Avoids occasional event loop issues on Windows terminals
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
