# test_cli.py
"""
Terminal-based test harness for FasalVachak DialogueManager.

Lets you type farmer input as text and see the agent's responses without
needing STT/TTS hooked up. Useful for rapid iteration on prompts and
dialogue logic.

Usage (from the FasalVachak/ project root):
    python test_cli.py
"""

from __future__ import annotations

import asyncio
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from dialogue.session import DialogueManager


DEBUG = False  # set False to hide phase/latency info


def print_debug(dm: DialogueManager, turn_latency: float | None = None) -> None:
    if not DEBUG:
        return
    print(
        f"    [debug] phase={dm.phase} | crop={dm.crop} | "
        f"questions_asked={dm.questions_asked} | followups_asked={dm.followups_asked}"
    )
    if turn_latency is not None:
        print(f"    [debug] turn latency: {turn_latency:.2f}s")


async def main() -> None:
    dm = DialogueManager()
    call_start = time.monotonic()

    print("=" * 60)
    print("FasalVachak — Dialogue Test CLI")
    print("Type farmer input in Hindi/Hinglish. 'quit' or 'exit' to stop.")
    print("=" * 60)
    print()
    print(
        "Agent: Namaste, KrishiSeva mein aapka swagat hai. "
        "Aapki dhaan ya kapas ki fasal mein kya lakshan dikh rahe hain, "
        "kripya bataiye?"
    )

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
            turn_start = time.monotonic()
            response = await dm.process_turn(farmer_input)
            turn_latency = time.monotonic() - turn_start
        except Exception as exc:
            print(f"\n[ERROR] {exc}")
            break

        print(f"\nAgent: {response}")
        print_debug(dm, turn_latency)

        if dm.phase == "completed":
            total = time.monotonic() - call_start
            print("\n--- Call complete (phase=completed). Restart for a new call. ---")
            print(f"--- Total elapsed time: {total:.2f}s ---")
            break


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())

