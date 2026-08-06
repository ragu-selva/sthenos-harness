"""Day 4 -- proof that a skill changes behavior with zero code changes.

Two Harness runs, identical code path and identical task, over two
directories that differ in exactly one way: scratch_skill_on/skills/
brand-voice/SKILL.md exists in one and not the other. catalog_prompt
advertises it in the system prompt whenever it's present; nothing tells
the model to load it -- the skill's own description has to be relevant
enough that the model decides to on its own. If the two runs' voices
differ, the skill did that, not a code change.

The skill file is written by this script rather than checked into the
repo -- it lives under demos/scratch_skill_on/, which is gitignored like
every other demo's scratch output, so a fresh clone needs nothing extra
to reproduce this.

Run it standalone:
    python demos/day4_verify_skill.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from Sthenos.harness import Harness

HERE = os.path.dirname(os.path.abspath(__file__))
WORKDIR_OFF = os.path.join(HERE, "scratch_skill_off")  # no skills/ directory
WORKDIR_ON = os.path.join(HERE, "scratch_skill_on")    # skills/brand-voice/SKILL.md present

TASK = "Write a two-sentence product description for a ceramic coffee mug."

PIRATE_MARKERS = ["arr", "ye ", "matey", "cap'n", "aye", "avast", "yer "]

BRAND_VOICE_SKILL = """---
description: Pirate voice for customer-facing marketing copy -- load this before writing any product description, tagline, or ad copy.
---
# Brand Voice: Pirate

All customer-facing copy -- product descriptions, taglines, ad copy -- is
written in the voice of a boisterous pirate sea captain, always:

- Use "arr", "ye", "matey", and nautical metaphors (ships, seas, treasure, crews).
- Favor exclamation over a flat, corporate tone.
- Still say what the product is and why it's good -- the voice changes, not the content.

Example: instead of "This mug keeps your coffee hot for hours," write
something like "This mug be keepin' yer grog steamin' hot through the
longest watch, arr!"
"""


def run(workdir, label, skill=False):
    os.makedirs(workdir, exist_ok=True)
    if skill:
        skill_dir = os.path.join(workdir, "skills", "brand-voice")
        os.makedirs(skill_dir, exist_ok=True)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(BRAND_VOICE_SKILL)
    calls = []
    agent = Harness(workdir, mode="yolo",
                     on_event=lambda kind, payload: calls.append(payload["name"])
                     if kind == "tool_start" else None)
    print(f"\n[{label}] workdir: {workdir}")
    print(f"[{label}] user: {TASK}")
    answer = agent.run(TASK)
    print(f"[{label}] assistant: {answer}")
    print(f"[{label}] tools called: {calls}")
    return answer


if __name__ == "__main__":
    plain = run(WORKDIR_OFF, "no skill")
    pirate = run(WORKDIR_ON, "with skill", skill=True)

    plain_hits = [m for m in PIRATE_MARKERS if m in plain.lower()]
    pirate_hits = [m for m in PIRATE_MARKERS if m in pirate.lower()]

    print(f"\n--- result ---")
    print(f"pirate markers in the no-skill run:   {plain_hits}")
    print(f"pirate markers in the with-skill run: {pirate_hits}")

    ok = not plain_hits and pirate_hits
    print("PASS: the skill changed the voice" if ok else "FAIL: no clear voice change")
    sys.exit(0 if ok else 1)
