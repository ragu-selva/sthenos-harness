"""Day 2 -- an agent that can build something.

Day 1 proved the loop turns; this proves it does work. The only new
wiring is real: six tools instead of one, and a policy in the
before_tool socket instead of a stub that always said yes. run_loop
itself is untouched -- that was the point of having the sockets.

The policy here is Policy("yolo"), which allows everything except the
deny patterns. That is deliberate for a demo you want to watch run, and
it is also the interesting case: yolo still refuses to delete your home
directory, because deny is checked before mode.

Run it with a task of your own:
    python demos/day2_build.py "count the lines in every file here"
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

from Sthenos import loop, provider, security, tools

SYSTEM = """You are Sthenos, a coding agent working in a scratch directory.
Use the tools to do the work rather than describing it. When you write code,
run it and report what actually happened. If a tool refuses, tell the user
plainly instead of trying to work around it."""

WORKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch")
DEFAULT_TASK = ("Create fib.py with an iterative fib(n), a __main__ printing fib(30), "
                "run it and confirm the output is 832040")

# Tool results can be an entire file; the transcript stays readable if the
# printer clips them, and the model still sees the whole thing.
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
    """Clip a value to one readable line for the transcript."""
    text = str(value).replace("\n", "\\n")
    return text if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS] + f"... (+{len(text) - PREVIEW_CHARS} chars)"


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,  # DEBUG replays every wire body; useful, very loud
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    os.makedirs(WORKDIR, exist_ok=True)
    task = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TASK

    registry = {t.name: t for t in tools.core_tools(WORKDIR)}
    policy = security.Policy("yolo")

    print(f"workdir: {WORKDIR}")
    print(f"tools:   {', '.join(registry)}")
    print(f"policy:  {policy.mode}")
    print(f"\nuser: {task}")

    answer = loop.run_loop(
        provider.DEFAULT_MODEL,
        SYSTEM,
        [{"role": "user", "text": task}],
        registry,
        print_event,
        policy.check,
    )
    print(f"\n--- final answer ---\n{answer}")
