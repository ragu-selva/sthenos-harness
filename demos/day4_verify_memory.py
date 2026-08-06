"""Day 4 -- proof that STHENOS.md survives past the conversation that wrote it.

memory.remember() writes a fact to STHENOS.md in one Harness run. This
script then builds a brand-new Harness -- a fresh message list, a fresh
session file, no prior turns -- over the same directory, and asks about
that fact. The only way the second run can answer correctly is
build_system_prompt folding STHENOS.md's contents into its system
prompt; the task explicitly forbids tool use, so a right answer can't
come from the agent reading the file itself mid-task.

Run it standalone:
    python demos/day4_verify_memory.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from Sthenos import memory
from Sthenos.harness import Harness

WORKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch_memory")
MARKER = "QUARTZ-8271"
FACT = f"The project's verification marker for today's check is {MARKER}."

if __name__ == "__main__":
    os.makedirs(WORKDIR, exist_ok=True)
    memory_path = os.path.join(WORKDIR, memory.MEMORY_FILE)
    if os.path.exists(memory_path):
        os.remove(memory_path)

    print(f"workdir: {WORKDIR}")
    print(f"conversation 1 -- remember() only, no model call")
    print(f"  {memory.remember(WORKDIR, FACT)}")

    print(f"\nconversation 2 -- a brand-new Harness, no shared state with conversation 1")
    tool_calls_made = []
    agent = Harness(WORKDIR, mode="read-only",
                     on_event=lambda kind, payload: tool_calls_made.append(payload)
                     if kind == "tool_start" else None)
    question = ("What is today's verification marker for this project? Answer with just "
                "the marker, on one line. Do not call any tools -- answer from what you "
                "already know.")
    print(f"user: {question}")
    answer = agent.run(question)
    print(f"assistant: {answer}")

    print(f"\n--- result ---")
    ok = MARKER in answer and not tool_calls_made
    if MARKER in answer:
        print(f"marker found in the answer: PASS")
    else:
        print(f"marker NOT found in the answer: FAIL")
    if tool_calls_made:
        print(f"but {len(tool_calls_made)} tool call(s) were made -- not answered from the "
              f"system prompt alone: {[c['name'] for c in tool_calls_made]}")
    else:
        print(f"zero tool calls made -- the answer came from the system prompt alone: PASS")
    sys.exit(0 if ok else 1)
