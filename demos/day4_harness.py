"""Day 4 -- the whole week, run through Harness.

Days 1-3 wired provider, loop, tools, security, and context together by
hand in each demo. Harness is that wiring done once, plus what day 3 and
4 added on top: STHENOS.md folded into the system prompt, a skills/
catalog offered the same way, spawn_agent for delegating self-contained
work, and every message durably logged to a session file as it happens.

This defaults to the same task day3_context.py used, at the same tight
budget, so a diff between the two output logs shows exactly what
Harness adds on top of a bare run_loop call: memory/skills sections in
the system prompt, a session file under .sthenos/sessions/, and two
extra tools (use_skill, spawn_agent) in the registry.

Run it with a task and budget of your own:
    python demos/day4_harness.py "task" 1500
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Model replies routinely contain emoji and smart quotes; a Windows console
# defaults to cp1252 and raises UnicodeEncodeError on them, which reads like
# the loop broke when it was only the printing that did.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from Sthenos import memory, session
from Sthenos.harness import Harness

WORKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch")
DEFAULT_TASK = ("Create five files one.txt through five.txt, each with 20 lines of the "
                "word ping, one write_file at a time with a read back after each; then "
                "MANIFEST.md listing each file and its line count verified with wc -l")
DEFAULT_BUDGET_TOKENS = 1500

# Sthenos.BASE_PROMPT is terser than day3_context.py's custom SYSTEM was, so
# the model finishes this task in fewer tokens than the budget by default --
# nothing to compact. Rather than hand-tune the prompt per demo, remember a
# working-style note once: memory shaping behavior across runs is what
# STHENOS.md is for, and it happens to be exactly enough narration to make
# budget_tokens=1500 bite mid-run, same as day3_context.py's system prompt did.
VERBOSITY_NOTE = ("Verify multi-file work item by item, not with one combined command, "
                   "narrating each step -- thoroughness over brevity.")

PREVIEW_CHARS = 400


def print_event(kind, payload):
    """Print each loop event as it happens, so the transcript reads turn by turn."""
    if kind == "assistant":
        if payload["text"]:
            print(f"\nassistant: {payload['text']}")
        for call in payload["tool_calls"]:
            print(f"\nassistant -> {call['name']}({_preview(call['args'])})")
    elif kind == "tool_end":
        print(f"   result: {_preview(payload['result'])}")


def _preview(value):
    text = str(value).replace("\n", "\\n")
    return text if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS] + f"... (+{len(text) - PREVIEW_CHARS} chars)"


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,  # DEBUG replays every wire body; INFO still shows compaction firing
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    os.makedirs(WORKDIR, exist_ok=True)
    task = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TASK
    budget_tokens = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BUDGET_TOKENS

    memory_path = os.path.join(WORKDIR, memory.MEMORY_FILE)
    already_noted = os.path.isfile(memory_path) and VERBOSITY_NOTE in open(
        memory_path, encoding="utf-8").read()
    if not already_noted:
        memory.remember(WORKDIR, VERBOSITY_NOTE)

    agent = Harness(WORKDIR, mode="yolo", budget_tokens=budget_tokens, on_event=print_event)

    print(f"workdir: {WORKDIR}")
    print(f"tools:   {', '.join(agent._registry())}")
    print(f"policy:  {agent.policy.mode}")
    print(f"budget:  {budget_tokens} tokens")
    print(f"\nuser: {task}")

    answer = agent.run(task)

    print(f"\n--- final answer ---\n{answer}")
    print(f"\nsession: {session.latest(WORKDIR)}")
