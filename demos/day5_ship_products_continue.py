"""Day 5 -- follow-up to day5_ship_products.py's phase 1: two projects needed a nudge.

taskman finished cleanly (9 turns, 18 tests passing). artisan-coffee got
stuck retrying a single write_file call for the whole page and kept hitting
the 8192-output-token ceiling; viper's turn ended with an empty response
after only a 170-byte stub, well short of the brief. Both get resumed
(same session, same file) with a corrective instruction rather than a
restart -- the failure is visible in their own history, so the fix is to
tell them what strategy to use, not to re-explain the task.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from Sthenos import Harness, run_fleet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTS_DIR = os.path.join(ROOT, "products")
LOG_CLIP = 200


def _clip(value, limit=LOG_CLIP):
    text = str(value)
    return text if len(text) <= limit else text[:limit] + f"...(+{len(text) - limit})"


def make_printer(name):
    def print_event(kind, payload):
        if kind == "assistant":
            if payload["text"]:
                print(f"[{name}] {_clip(payload['text'])}")
            for call in payload["tool_calls"]:
                print(f"[{name}] -> {call['name']}({_clip(call['args'])})")
        elif kind == "tool_end":
            print(f"[{name}]    = {_clip(payload['result'])}")
    return print_event


NUDGES = {
    "artisan-coffee": (
        "Stop trying to write the entire page in one write_file call -- your own history "
        "shows that keeps failing because the response is cut off before the content "
        "argument finishes, so write_file never even receives it. Build (or, if index.html "
        "already has a small placeholder, replace it with) a real but minimal skeleton first "
        "-- doctype, head with the CSS custom properties for the design system, empty section "
        "elements with ids for each required section -- via one write_file call kept well "
        "under 2000 characters. Then add real content section by section using edit_file, one "
        "section per call. Keep going until every requirement in the design-engineering skill "
        "and your original task is met, then do the skill's self-review pass."
    ),
    "viper": (
        "index.html is currently just a small stub -- the game has not actually been built "
        "yet. Continue: build out the full snake game and page now. Write index.html in "
        "small pieces (a skeleton first, then edit_file for the CSS, then edit_file for the "
        "game JS, then edit_file for page chrome/copy) rather than one giant write_file call, "
        "since a single very large write_file response can get cut off. Meet every requirement "
        "in your original task and the design-engineering skill, then do the skill's "
        "self-review pass before finishing."
    ),
}


def main():
    jobs = [{"name": name, "workdir": os.path.join(PRODUCTS_DIR, name), "task": task}
            for name, task in NUDGES.items()]
    workdir_to_name = {job["workdir"]: job["name"] for job in jobs}

    def make_harness(workdir):
        name = workdir_to_name[workdir]
        agent = Harness(workdir, on_event=make_printer(name))
        agent.resume()
        return agent

    results = run_fleet(jobs, make_harness, max_workers=2)
    for r in results:
        print(f"\n--- continue/{r['name']} ok={r['ok']} ---\n{_clip(r['report'], 2000)}")
    return results


if __name__ == "__main__":
    main()
