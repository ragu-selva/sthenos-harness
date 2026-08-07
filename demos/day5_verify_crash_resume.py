"""Day 5 verification 1/2 -- resume() survives a kill -9 mid-task.

Run with "start" to launch the multi-file task (meant to be killed partway
through, e.g. `kill -9 <pid>`), or "continue" to resume() the same workdir
and finish the task in a fresh process. Not part of the test suite --
tests/ only fakes the network; this is the live-API check the day-5 prompt
asked for.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from Sthenos import session
from Sthenos.harness import Harness

WORKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch_day5_crash")
TASK = ("Create part1.txt through part5.txt one at a time -- write_file then read_file "
        "each one back before moving to the next -- then SUMMARY.md describing each file "
        "in one line. Narrate each step before acting.")


def print_event(kind, payload):
    if kind == "assistant":
        if payload["text"]:
            print(f"\nassistant: {payload['text']}")
        for call in payload["tool_calls"]:
            print(f"assistant -> {call['name']}({call['args']})")
    elif kind == "tool_end":
        print(f"   result: {str(payload['result'])[:200]}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "start"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    os.makedirs(WORKDIR, exist_ok=True)
    agent = Harness(WORKDIR, on_event=print_event)

    if mode == "continue":
        resumed = agent.resume()
        print(f"resume() -> {resumed}, session={agent.session_path}")
        answer = agent.run("continue the task")
    else:
        print(f"pid={os.getpid()} workdir={WORKDIR}")
        answer = agent.run(TASK)

    print(f"\n--- final answer ---\n{answer}")
    print(f"session: {session.latest(WORKDIR)}")
