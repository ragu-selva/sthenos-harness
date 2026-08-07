"""Test suite for taskman.py.

Drives the CLI via subprocess against a temporary JSON store, without
importing any of taskman's internals.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

TASKMAN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taskman.py")


def run(store, *args):
    """Run `python taskman.py -f store <args>` and return CompletedProcess."""
    cmd = [sys.executable, TASKMAN, "-f", store] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


class TaskmanTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.store = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store)  # taskman should create it itself on first save

    def tearDown(self):
        if os.path.exists(self.store):
            os.remove(self.store)
        tmp = self.store + ".tmp"
        if os.path.exists(tmp):
            os.remove(tmp)

    def load_store(self):
        with open(self.store, "r", encoding="utf-8") as fh:
            return json.load(fh)

    # -- add -----------------------------------------------------------

    def test_add_creates_task_with_defaults(self):
        result = run(self.store, "add", "buy milk")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Added task 1", result.stdout)

        tasks = self.load_store()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["description"], "buy milk")
        self.assertEqual(tasks[0]["priority"], "medium")
        self.assertEqual(tasks[0]["status"], "pending")

    def test_add_with_priority(self):
        result = run(self.store, "add", "urgent thing", "-p", "high")
        self.assertEqual(result.returncode, 0)
        tasks = self.load_store()
        self.assertEqual(tasks[0]["priority"], "high")

    def test_add_assigns_incrementing_ids(self):
        run(self.store, "add", "first")
        run(self.store, "add", "second")
        tasks = self.load_store()
        ids = sorted(t["id"] for t in tasks)
        self.assertEqual(ids, [1, 2])

    def test_add_empty_description_fails(self):
        result = run(self.store, "add", "   ")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error", result.stderr.lower())
        self.assertFalse(os.path.exists(self.store))

    def test_add_invalid_priority_fails(self):
        result = run(self.store, "add", "task", "-p", "urgent")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr.lower())

    # -- list ------------------------------------------------------------

    def test_list_empty_store(self):
        result = run(self.store, "list")
        self.assertEqual(result.returncode, 0)
        self.assertIn("No tasks found.", result.stdout)

    def test_list_shows_table_with_headers_and_rows(self):
        run(self.store, "add", "buy milk", "-p", "high")
        run(self.store, "add", "write report")
        result = run(self.store, "list")
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.splitlines()
        self.assertIn("ID", lines[0])
        self.assertIn("PRIORITY", lines[0])
        self.assertIn("STATUS", lines[0])
        self.assertIn("DESCRIPTION", lines[0])
        # Header, separator, then one row per task.
        self.assertEqual(len(lines), 4)
        self.assertIn("buy milk", result.stdout)
        self.assertIn("write report", result.stdout)

    def test_list_filter_by_status(self):
        run(self.store, "add", "task a")
        run(self.store, "add", "task b")
        run(self.store, "done", "1")
        result = run(self.store, "list", "-s", "done")
        self.assertEqual(result.returncode, 0)
        self.assertIn("task a", result.stdout)
        self.assertNotIn("task b", result.stdout)

    def test_list_filter_by_priority(self):
        run(self.store, "add", "low task", "-p", "low")
        run(self.store, "add", "high task", "-p", "high")
        result = run(self.store, "list", "-p", "high")
        self.assertEqual(result.returncode, 0)
        self.assertIn("high task", result.stdout)
        self.assertNotIn("low task", result.stdout)

    # -- done --------------------------------------------------------------

    def test_done_marks_task_complete(self):
        run(self.store, "add", "buy milk")
        result = run(self.store, "done", "1")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Marked task 1 as done", result.stdout)
        tasks = self.load_store()
        self.assertEqual(tasks[0]["status"], "done")
        self.assertIsNotNone(tasks[0]["done_at"])

    def test_done_nonexistent_id_fails(self):
        result = run(self.store, "done", "42")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no task with id 42", result.stderr)

    def test_done_already_done_fails(self):
        run(self.store, "add", "buy milk")
        run(self.store, "done", "1")
        result = run(self.store, "done", "1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already done", result.stderr)

    # -- rm ------------------------------------------------------------

    def test_rm_removes_task(self):
        run(self.store, "add", "buy milk")
        run(self.store, "add", "write report")
        result = run(self.store, "rm", "1")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Removed task 1", result.stdout)
        tasks = self.load_store()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["description"], "write report")

    def test_rm_nonexistent_id_fails(self):
        result = run(self.store, "rm", "5")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no task with id 5", result.stderr)

    # -- stats ---------------------------------------------------------

    def test_stats_empty_store(self):
        result = run(self.store, "stats")
        self.assertEqual(result.returncode, 0)
        self.assertIn("No tasks found.", result.stdout)

    def test_stats_counts(self):
        run(self.store, "add", "a", "-p", "high")
        run(self.store, "add", "b", "-p", "high")
        run(self.store, "add", "c", "-p", "low")
        run(self.store, "done", "1")
        result = run(self.store, "stats")
        self.assertEqual(result.returncode, 0)
        out = result.stdout
        self.assertIn("total", out)
        self.assertIn("3", out)
        self.assertIn("pending", out)
        self.assertIn("done", out)
        self.assertIn("high", out)
        self.assertIn("low", out)

    # -- misc / cross-cutting -------------------------------------------

    def test_unknown_command_fails(self):
        result = run(self.store, "frobnicate")
        self.assertNotEqual(result.returncode, 0)

    def test_full_workflow(self):
        self.assertEqual(run(self.store, "add", "task 1").returncode, 0)
        self.assertEqual(run(self.store, "add", "task 2", "-p", "low").returncode, 0)
        self.assertEqual(run(self.store, "done", "1").returncode, 0)
        result = run(self.store, "list", "-s", "pending")
        self.assertIn("task 2", result.stdout)
        self.assertNotIn("task 1", result.stdout)
        self.assertEqual(run(self.store, "rm", "2").returncode, 0)
        tasks = self.load_store()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], 1)
        self.assertEqual(tasks[0]["status"], "done")


if __name__ == "__main__":
    unittest.main()
