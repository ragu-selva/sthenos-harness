"""Day 5 verification 1b -- resume() + run() over a genuinely torn session.

Companion to day5_verify_crash_resume.py: that script proved a live kill -9
against this design almost always lands after the tool result is already
flushed (see the day-5 summary for why). This script exercises the other
half directly -- a session file crafted to have a real dangling tool_call,
the exact shape session._repair() exists for -- through the live resume()
and run() path, against the real API.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from Sthenos import session
from Sthenos.harness import Harness

WORKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch_day5_repair")


def print_event(kind, payload):
    if kind == "assistant":
        if payload["text"]:
            print(f"\nassistant: {payload['text']}")
        for call in payload["tool_calls"]:
            print(f"assistant -> {call['name']}({call['args']})")
    elif kind == "tool_end":
        print(f"   result: {str(payload['result'])[:200]}")


if __name__ == "__main__":
    agent = Harness(WORKDIR, on_event=print_event)
    resumed = agent.resume()
    print(f"resume() -> {resumed}")
    print("loaded messages:")
    for m in agent.messages:
        print(" ", m)

    answer = agent.run("continue the task")
    print(f"\n--- final answer ---\n{answer}")
    print(f"\nfiles: {sorted(os.listdir(WORKDIR))}")
    print(f"session: {session.latest(WORKDIR)}")
