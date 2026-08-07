"""Day 5 -- the front door: sthenos as a command you type.

Every prior day proved itself through a demos/day*.py script that wired a
Harness by hand and printed events to stdout. That's the whole shape of a
CLI already -- this file just makes it the real one: argparse instead of
sys.argv[1], one prompt-and-run for -p, a REPL when there isn't one, and
--resume plugging into Harness.resume() instead of a demo re-deriving it.

Design rules:
  - headless and interactive share one Harness. -p builds it, optionally
    resumes it, runs one task, and exits; the REPL builds the same kind of
    object and calls run() once per line instead of once total. Neither
    path gets its own copy of the wiring.
  - the approver is a person, not a policy. Policy.check already decides
    what needs asking; make_approver only renders the question and reads
    y/N -- the decision of what counts as dangerous stays in security.py.
  - Ctrl-C interrupts a run, not the process. The session file is durable
    the moment each message lands (harness.py's _flush), so the honest
    thing to print is "still on disk, --resume continues it" -- not to
    swallow the interrupt and pretend the run finished.
"""

import argparse

from .harness import Harness
from .security import MODES, Policy

ARGS_CLIP = 120
RESULT_CLIP = 200
DIM, RESET = "\x1b[2m", "\x1b[0m"


def _clip(value, limit):
    text = str(value)
    return text if len(text) <= limit else text[:limit] + f"...(+{len(text) - limit})"


def print_event(kind, payload):
    """The default on_event: assistant text plain, each tool call on one line, its result dimmed under it."""
    if kind == "assistant":
        if payload["text"]:
            print(payload["text"])
        for call in payload["tool_calls"]:
            print(f"-> {call['name']}({_clip(call['args'], ARGS_CLIP)})")
    elif kind == "tool_end":
        first_line = str(payload["result"]).splitlines()[0] if payload["result"] else ""
        print(f"{DIM}   {_clip(first_line, RESULT_CLIP)}{RESET}")


def make_approver():
    """An approver that shows the call and asks the terminal for a y/N."""

    def approve(call, reason):
        print(f"{call['name']}({_clip(call['args'], ARGS_CLIP)}) -- {reason}")
        return input("approve this call? [y/N] ").strip().lower() == "y"

    return approve


def build_parser():
    parser = argparse.ArgumentParser(prog="sthenos", description="The smallest agent harness.")
    parser.add_argument("-p", "--prompt", help="run one task headlessly and exit")
    parser.add_argument("-d", "--workdir", default=".", help="working directory (default: .)")
    parser.add_argument("-m", "--model", default=None, help="model to use")
    parser.add_argument("--mode", choices=MODES, default=None,
                         help="policy mode (default: safe interactively, yolo with -p)")
    parser.add_argument("--resume", action="store_true", help="resume the latest session in workdir")
    parser.add_argument("--max-turns", type=int, default=120, help="turn limit per run (default 120)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    headless = args.prompt is not None
    mode = args.mode or ("yolo" if headless else "safe")
    policy = Policy(mode, approver=None if headless else make_approver())
    agent = Harness(args.workdir, model=args.model, policy=policy,
                     on_event=print_event, max_turns=args.max_turns)

    if headless:
        if args.resume:
            agent.resume()
        agent.run(args.prompt)
        return 0

    print(f"sthenos -- model={agent.model} mode={policy.mode} dir={agent.workdir}")
    if args.resume:
        print("resumed." if agent.resume() else "nothing to resume.")

    while True:
        try:
            task = input("> ")
        except EOFError:
            print()
            return 0
        if not task.strip():
            continue
        try:
            print(agent.run(task))
        except KeyboardInterrupt:
            print("\ninterrupted -- the session log is safe; rerun with --resume to continue it")

    return 0
