#!/usr/bin/env python3
"""taskman - a small command-line task manager.

Tasks are persisted as JSON in a local file (default: tasks.json in the
current directory, override with --file/-f).

Subcommands:
    add    - add a new task
    list   - list tasks (optionally filtered) in a fixed-width table
    done   - mark a task as done
    rm     - remove a task
    stats  - show summary statistics in a fixed-width table
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

DEFAULT_FILE = "tasks.json"
PRIORITIES = ["low", "medium", "high"]
STATUSES = ["pending", "done"]


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_tasks(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
    except OSError as exc:
        print(f"error: could not read store '{path}': {exc}", file=sys.stderr)
        sys.exit(1)
    if not content:
        return []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        print(f"error: store '{path}' is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, list):
        print(f"error: store '{path}' does not contain a task list", file=sys.stderr)
        sys.exit(1)
    return data


def save_tasks(path, tasks):
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(tasks, fh, indent=2)
        fh.write("\n")
    os.replace(tmp_path, path)


def next_id(tasks):
    if not tasks:
        return 1
    return max(t["id"] for t in tasks) + 1


def find_task(tasks, task_id):
    for t in tasks:
        if t["id"] == task_id:
            return t
    return None


def truncate(text, width):
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def print_table(headers, rows, widths):
    def fmt_row(cols):
        return "  ".join(
            truncate(str(c), w).ljust(w) for c, w in zip(cols, widths)
        )

    print(fmt_row(headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt_row(row))


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_add(args):
    tasks = load_tasks(args.file)
    description = args.description.strip()
    if not description:
        print("error: description must not be empty", file=sys.stderr)
        sys.exit(1)

    task = {
        "id": next_id(tasks),
        "description": description,
        "priority": args.priority,
        "status": "pending",
        "created_at": now_iso(),
        "done_at": None,
    }
    tasks.append(task)
    save_tasks(args.file, tasks)
    print(f"Added task {task['id']}: {description}")


def cmd_list(args):
    tasks = load_tasks(args.file)

    if args.status != "all":
        tasks = [t for t in tasks if t["status"] == args.status]
    if args.priority is not None:
        tasks = [t for t in tasks if t["priority"] == args.priority]

    if not tasks:
        print("No tasks found.")
        return

    tasks = sorted(tasks, key=lambda t: t["id"])

    widths = [4, 8, 8, 50, 19]
    headers = ["ID", "PRIORITY", "STATUS", "DESCRIPTION", "CREATED"]
    rows = [
        [
            t["id"],
            t["priority"],
            t["status"],
            t["description"],
            t["created_at"],
        ]
        for t in tasks
    ]
    print_table(headers, rows, widths)


def cmd_done(args):
    tasks = load_tasks(args.file)
    task = find_task(tasks, args.id)
    if task is None:
        print(f"error: no task with id {args.id}", file=sys.stderr)
        sys.exit(1)
    if task["status"] == "done":
        print(f"error: task {args.id} is already done", file=sys.stderr)
        sys.exit(1)
    task["status"] = "done"
    task["done_at"] = now_iso()
    save_tasks(args.file, tasks)
    print(f"Marked task {args.id} as done")


def cmd_rm(args):
    tasks = load_tasks(args.file)
    task = find_task(tasks, args.id)
    if task is None:
        print(f"error: no task with id {args.id}", file=sys.stderr)
        sys.exit(1)
    tasks = [t for t in tasks if t["id"] != args.id]
    save_tasks(args.file, tasks)
    print(f"Removed task {args.id}")


def cmd_stats(args):
    tasks = load_tasks(args.file)

    total = len(tasks)
    if total == 0:
        print("No tasks found.")
        return

    done_count = sum(1 for t in tasks if t["status"] == "done")
    pending_count = total - done_count

    widths = [10, 8]
    print_table(
        ["METRIC", "COUNT"],
        [
            ["total", total],
            ["pending", pending_count],
            ["done", done_count],
        ],
        widths,
    )
    print()

    priority_rows = []
    for p in PRIORITIES:
        priority_rows.append([p, sum(1 for t in tasks if t["priority"] == p)])
    print_table(["PRIORITY", "COUNT"], priority_rows, widths)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="taskman", description="A small command-line task manager."
    )
    parser.add_argument(
        "-f",
        "--file",
        default=DEFAULT_FILE,
        help=f"path to the JSON task store (default: {DEFAULT_FILE})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_add = subparsers.add_parser("add", help="add a new task")
    p_add.add_argument("description", help="task description")
    p_add.add_argument(
        "-p",
        "--priority",
        choices=PRIORITIES,
        default="medium",
        help="task priority (default: medium)",
    )
    p_add.set_defaults(func=cmd_add)

    p_list = subparsers.add_parser("list", help="list tasks")
    p_list.add_argument(
        "-s",
        "--status",
        choices=STATUSES + ["all"],
        default="all",
        help="filter by status (default: all)",
    )
    p_list.add_argument(
        "-p",
        "--priority",
        choices=PRIORITIES,
        default=None,
        help="filter by priority",
    )
    p_list.set_defaults(func=cmd_list)

    p_done = subparsers.add_parser("done", help="mark a task as done")
    p_done.add_argument("id", type=int, help="task id")
    p_done.set_defaults(func=cmd_done)

    p_rm = subparsers.add_parser("rm", help="remove a task")
    p_rm.add_argument("id", type=int, help="task id")
    p_rm.set_defaults(func=cmd_rm)

    p_stats = subparsers.add_parser("stats", help="show task statistics")
    p_stats.set_defaults(func=cmd_stats)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
