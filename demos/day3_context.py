"""Day 3 -- an agent whose transcript outgrows its budget mid-task.

Day 2 proved the loop does real work; this proves it keeps doing real
work once the message list gets too big to send as-is. The only new
wiring is context.compact plugged into before_turn, exactly the socket
loop.py has carried since day 1 -- run_loop itself is still untouched.

A small budget_tokens makes compaction fire within one run instead of
after days of use. The default task is chosen to need it: five
write-then-read-back round trips plus a manifest step generate enough
tool traffic that even a few thousand tokens of budget is exceeded
partway through, and context.compact logs an INFO line every time it
fires -- watch for "compacted N messages" below.

Run it with a task and budget of your own:
    python demos/day3_context.py "task" 1500
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

from Sthenos import context, loop, provider, security, tools

SYSTEM = """You are Sthenos, a coding agent working in a scratch directory.
Use the tools to do the work rather than describing it. When you write code,
run it and report what actually happened. If a tool refuses, tell the user
plainly instead of trying to work around it. Narrate each step in a sentence
or two before acting, and verify line counts with a separate wc -l call per
file rather than one combined command -- thorough, not terse."""

WORKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch")
DEFAULT_TASK = ("Create five files one.txt through five.txt, each with 20 lines of the "
                "word ping, one write_file at a time with a read back after each; then "
                "MANIFEST.md listing each file and its line count verified with wc -l")
DEFAULT_BUDGET_TOKENS = 1500

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
        level=logging.INFO,  # DEBUG replays every wire body; INFO still shows compaction firing
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    os.makedirs(WORKDIR, exist_ok=True)
    task = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TASK
    budget_tokens = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BUDGET_TOKENS
    model = provider.DEFAULT_MODEL

    registry = {t.name: t for t in tools.core_tools(WORKDIR)}
    policy = security.Policy("yolo")

    print(f"workdir: {WORKDIR}")
    print(f"tools:   {', '.join(registry)}")
    print(f"policy:  {policy.mode}")
    print(f"budget:  {budget_tokens} tokens (~{budget_tokens * context.CHARS_PER_TOKEN} chars)")
    print(f"\nuser: {task}")

    answer = loop.run_loop(
        model,
        SYSTEM,
        [{"role": "user", "text": task}],
        registry,
        print_event,
        policy.check,
        before_turn=lambda msgs: context.compact(model, msgs, budget_tokens),
    )
    print(f"\n--- final answer ---\n{answer}")
