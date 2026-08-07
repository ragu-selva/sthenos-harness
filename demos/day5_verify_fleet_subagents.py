"""Day 5 verification 2/2 -- spawn_agent delegates, children stay off the parent's session.

Two children write utils.py and test_utils.py; the parent runs the tests
itself rather than delegating that too, and only the parent's session file
should exist under .sthenos/sessions -- children are built with
persist=False (see Harness._make_child), so a sub-agent's throwaway
conversation can never shadow --resume.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from Sthenos import session
from Sthenos.harness import Harness

WORKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch_day5_fleet")
TASK = ("Use spawn_agent twice: delegate writing utils.py with a slugify(text) function to "
        "one child, and test_utils.py with five asserts to another; then run "
        "python3 test_utils.py yourself and report.")


def print_event(kind, payload):
    if kind == "assistant":
        if payload["text"]:
            print(f"\nassistant: {payload['text']}")
        for call in payload["tool_calls"]:
            print(f"assistant -> {call['name']}({str(call['args'])[:200]})")
    elif kind == "tool_end":
        print(f"   result: {str(payload['result'])[:300]}")


if __name__ == "__main__":
    os.makedirs(WORKDIR, exist_ok=True)
    agent = Harness(WORKDIR, on_event=print_event)
    answer = agent.run(TASK)

    print(f"\n--- final answer ---\n{answer}")
    print(f"\nfiles: {sorted(os.listdir(WORKDIR))}")
    sessions_dir = os.path.join(WORKDIR, ".sthenos", "sessions")
    files = sorted(os.listdir(sessions_dir)) if os.path.isdir(sessions_dir) else []
    print(f"session files ({len(files)}): {files}")
