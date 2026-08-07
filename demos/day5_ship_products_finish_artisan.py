"""Day 5 -- finish artisan-coffee's review pass, interrupted twice by API credit outages.

taskman and viper's review-and-fix passes completed and passed mechanical
verification already. artisan-coffee found its 12 deficiencies (backed by a
real WCAG contrast audit) and was partway through fixing them -- #1, #2,
#3, #11, #12 confirmed done in the log -- when the second credit outage
hit. This resumes that same session with a continuation, not a restart.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from Sthenos import Harness

WORKDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "products", "artisan-coffee")

TASK = ("Continue fixing the remaining items from the 12-deficiency list you already "
        "identified and started fixing -- you'd confirmed #1, #2, #3, #11, and #12 done "
        "before being interrupted. Finish the rest, then verify again: re-run your checks "
        "(tag balance, contrast, word/section/SVG/interaction counts) and confirm the page "
        "still meets the design-engineering skill bar.")


def print_event(kind, payload):
    if kind == "assistant":
        if payload["text"]:
            print(f"assistant: {payload['text'][:400]}")
        for call in payload["tool_calls"]:
            print(f"assistant -> {call['name']}({str(call['args'])[:150]})")
    elif kind == "tool_end":
        print(f"   result: {str(payload['result'])[:200]}")


if __name__ == "__main__":
    agent = Harness(WORKDIR, on_event=print_event)
    resumed = agent.resume()
    print(f"resume() -> {resumed}, session={agent.session_path}")
    answer = agent.run(TASK)
    print(f"\n--- final answer ---\n{answer}")
