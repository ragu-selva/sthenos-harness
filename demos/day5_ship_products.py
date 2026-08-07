"""Day 5 -- prove the harness by shipping real products with it.

Three run_fleet jobs, two phases each: a build pass, then a second run()
over the *same* session (resume() before run(), not a fresh Harness) asking
the model to review its own work as a demanding design director, list a
dozen concrete deficiencies, and fix them. Every project gets
skills/design-engineering/SKILL.md -- the quality bar this file's user
specified -- so both passes are graded against the same written bar rather
than the model's unstated taste.

Not part of the test suite (it costs real API calls and real wall time);
run directly: `python demos/day5_ship_products.py`.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from Sthenos import Harness, run_fleet
from Sthenos import session as session_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTS_DIR = os.path.join(ROOT, "products")

SKILL_MD = """---
description: The quality bar for a real product surface -- design system, real copy, hand-drawn SVGs, working interactivity, responsiveness, and a self-review pass before calling anything done.
---

# Design Engineering

Hold every visual/product deliverable to this bar:

- a real design system as CSS custom properties
- at least 9 distinct sections for a landing page
- at least 1,200 words of real copy, no lorem ipsum
- at least 4 hand-drawn inline SVG illustrations, one being a product artifact in the hero
- at least 3 working interactive behaviors
- responsive at 360, 768, and 1280
- semantic HTML with focus states
- a self-review pass before finishing that counts sections, words, SVGs, and interactions against these minimums and fixes any shortfall
"""

PROJECTS = {
    "artisan-coffee": (
        "Build a single self-contained index.html (inline CSS and JS, no external "
        "dependencies or CDN links) for a specialty coffee roaster based in Goa. Load and "
        "follow the design-engineering skill's quality bar throughout -- it applies in full. "
        "Required, specifically: a sticky nav; a hero section whose drawn product artifact "
        "(inline SVG) anchors the page; six origin cards, each with a price; a three-tier "
        "subscription pricing table with a working monthly/annual price toggle; a brew-guide "
        "section with tabs; an FAQ accordion; a dark-mode toggle whose choice persists across "
        "reloads via localStorage."
    ),
    "taskman": (
        "Build a Python command-line task manager in this directory. argparse subcommands: "
        "add, list, done, rm, stats. Persist tasks as JSON in a local file. list/stats output "
        "as an aligned, fixed-width table. Write a unittest test suite of at least 10 cases, "
        "in a file named test_taskman.py, that drives the CLI via subprocess (not by importing "
        "its internals) against a temporary JSON store, covering each subcommand and at least "
        "one error path. Run the suite yourself until every test passes, then report the final "
        "pass count."
    ),
    "viper": (
        "Build a single self-contained index.html (inline CSS and JS, no external dependencies "
        "or CDN links) implementing a snake game on an HTML canvas. Load and follow the "
        "design-engineering skill's quality bar for anything outside the game canvas itself "
        "(page chrome, instructions, etc.). The game itself requires: grid-based movement "
        "driven by requestAnimationFrame; food that respawns after being eaten; speed that "
        "increases every 5 food eaten; a visible score; pause and restart controls; a high "
        "score persisted across reloads via localStorage."
    ),
}

REVIEW_TASK = ("Review every file you produced against the skill bar as a demanding design "
               "director; list 12 concrete deficiencies; fix them all; verify again.")

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


def setup_workdirs():
    for name in PROJECTS:
        wd = os.path.join(PRODUCTS_DIR, name)
        skill_dir = os.path.join(wd, "skills", "design-engineering")
        os.makedirs(skill_dir, exist_ok=True)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(SKILL_MD)
    return {name: os.path.join(PRODUCTS_DIR, name) for name in PROJECTS}


def run_build_phase(workdirs):
    jobs = [{"name": name, "workdir": workdirs[name], "task": task}
            for name, task in PROJECTS.items()]

    def make_harness(workdir):
        name = next(n for n, wd in workdirs.items() if wd == workdir)
        return Harness(workdir, on_event=make_printer(name))

    return run_fleet(jobs, make_harness, max_workers=3)


def run_review_phase(workdirs):
    jobs = [{"name": name, "workdir": workdirs[name], "task": REVIEW_TASK} for name in PROJECTS]

    def make_harness(workdir):
        name = next(n for n, wd in workdirs.items() if wd == workdir)
        agent = Harness(workdir, on_event=make_printer(name))
        agent.resume()
        return agent

    return run_fleet(jobs, make_harness, max_workers=3)


# --- mechanical verification, independent of anything the model reported ---

def _visible_word_count(html_path):
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&[a-zA-Z#0-9]+;", " ", html)
    return len(html.split())


def _contains(path, needle):
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as f:
        return needle.lower() in f.read().lower()


def verify_artisan_coffee(wd):
    checks = {}
    html = os.path.join(wd, "index.html")
    checks["index.html exists"] = os.path.isfile(html)
    if checks["index.html exists"]:
        checks["localStorage present (grep)"] = _contains(html, "localStorage")
        checks["accordion present (grep)"] = _contains(html, "accordion")
        wc = _visible_word_count(html)
        checks[f"visible word count >= 1200 (got {wc})"] = wc >= 1200
    return checks


def verify_viper(wd):
    checks = {}
    html = os.path.join(wd, "index.html")
    checks["index.html exists"] = os.path.isfile(html)
    if checks["index.html exists"]:
        checks["requestAnimationFrame present (grep)"] = _contains(html, "requestAnimationFrame")
        checks["localStorage present (grep)"] = _contains(html, "localStorage")
    return checks


def verify_taskman(wd):
    checks = {}
    py_files = [f for f in os.listdir(wd) if f.endswith(".py")] if os.path.isdir(wd) else []
    checks["python source files exist"] = bool(py_files)
    test_files = [f for f in py_files if "test" in f.lower()]
    checks["a test file exists"] = bool(test_files)
    if test_files:
        proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-p", "*test*.py", "-v"],
                               cwd=wd, capture_output=True, text=True, timeout=180)
        checks[f"unittest suite passes (exit {proc.returncode})"] = proc.returncode == 0
        checks["_test_tail"] = (proc.stdout + proc.stderr)[-2000:]
    return checks


def count_turns(workdir):
    path = session_mod.latest(workdir)
    if not path:
        return 0
    return sum(1 for m in session_mod.load(path) if m.get("role") == "assistant")


def main():
    workdirs = setup_workdirs()

    print("=== PHASE 1: build ===")
    build_results = run_build_phase(workdirs)
    for r in build_results:
        print(f"\n--- build/{r['name']} ok={r['ok']} ---\n{_clip(r['report'], 1500)}")

    print("\n=== PHASE 2: review as a demanding design director, fix, verify ===")
    review_results = run_review_phase(workdirs)
    for r in review_results:
        print(f"\n--- review/{r['name']} ok={r['ok']} ---\n{_clip(r['report'], 1500)}")

    print("\n=== mechanical verification ===")
    checks_by_project = {
        "artisan-coffee": verify_artisan_coffee(workdirs["artisan-coffee"]),
        "taskman": verify_taskman(workdirs["taskman"]),
        "viper": verify_viper(workdirs["viper"]),
    }

    print("\n=== RESULTS ===")
    print(f"{'project':<16}{'pass/fail':<10}{'turns':<8}checks")
    for name, checks in checks_by_project.items():
        visible = {k: v for k, v in checks.items() if not k.startswith("_")}
        passed = all(visible.values())
        turns = count_turns(workdirs[name])
        print(f"{name:<16}{'PASS' if passed else 'FAIL':<10}{turns:<8}")
        for k, v in visible.items():
            print(f"    [{'x' if v else ' '}] {k}")

    return checks_by_project


if __name__ == "__main__":
    main()
