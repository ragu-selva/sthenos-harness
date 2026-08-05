"""Day 1 -- the smallest possible agent.

One hand-written tool, a printing observer, and a gate that always says
yes. Nothing here is generic yet -- no tool registry, no schema
generation, no policy engine -- on purpose: day 1 proves the loop works
end to end before day 2 onward makes any of those pieces reusable.

Design rules this file embodies:
  - the tool is a plain object with .spec and .run; run_loop doesn't
    care that it's hand-written instead of decorator-generated.
  - before_tool here is the simplest legal gate (always allow), so the
    transcript below shows the loop's own behavior, not a policy's.
  - on_event is the only window into what happened; day 1 just prints it.
"""

import logging
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Model replies routinely contain emoji and smart quotes; a Windows console
# defaults to cp1252 and raises UnicodeEncodeError on them, which reads like
# the loop broke when it was only the printing that did.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from Sthenos import loop, provider

SYSTEM = "You are Sthenos, a minimal agent. Use tools when they help; otherwise answer directly."


class RollDice:
    """Roll count six-sided dice and report each result."""

    spec = {"schema": {
        "name": "roll_dice",
        "description": "Roll count six-sided dice",
        "parameters": {
            "type": "object",
            "properties": {"count": {"type": "string", "description": "How many dice"}},
            "required": ["count"],
        },
    }}

    def run(self, count):
        """Roll int(count) six-sided dice; return the list of results."""
        return [random.randint(1, 6) for _ in range(int(count))]


def print_event(kind, payload):
    """Print each loop event as it happens, so the transcript reads turn by turn."""
    if kind == "assistant":
        if payload["text"]:
            print(f"assistant: {payload['text']}")
        for call in payload["tool_calls"]:
            print(f"assistant -> tool call: {call['name']}({call['args']})")
    elif kind == "tool_end":
        print(f"tool result ({payload['name']}): {payload['result']}")


def always_allow(call):
    """Allow every tool call -- day 1 has no policy layer yet."""
    return None


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    task = "Roll 3 dice and tell me whether the total beats 10"
    print(f"user: {task}")
    loop.run_loop(
        provider.DEFAULT_MODEL,
        SYSTEM,
        [{"role": "user", "text": task}],
        {"roll_dice": RollDice()},
        print_event,
        always_allow,
    )
