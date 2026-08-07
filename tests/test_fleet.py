"""Tests for Sthenos.fleet -- run_fleet, against a fake agent, no real Harness or network."""

import time

from Sthenos import fleet


class FakeAgent:
    """Stands in for a Harness: either sleeps then returns text, or raises."""

    def __init__(self, behavior):
        self.behavior = behavior

    def run(self, task):
        kind, value = self.behavior
        if kind == "sleep_return":
            delay, text = value
            time.sleep(delay)
            return text
        raise value


def make_harness_factory(behavior_by_workdir):
    def make_harness(workdir):
        return FakeAgent(behavior_by_workdir[workdir])
    return make_harness


def test_results_come_back_in_job_order_not_completion_order():
    jobs = [
        {"name": "slow", "workdir": "a", "task": "x"},
        {"name": "fast", "workdir": "b", "task": "x"},
    ]
    make_harness = make_harness_factory({
        "a": ("sleep_return", (0.05, "slow done")),
        "b": ("sleep_return", (0.0, "fast done")),
    })

    results = fleet.run_fleet(jobs, make_harness, max_workers=2)

    assert [r["name"] for r in results] == ["slow", "fast"]
    assert results[0] == {"name": "slow", "ok": True, "report": "slow done"}
    assert results[1] == {"name": "fast", "ok": True, "report": "fast done"}


def test_a_failing_job_becomes_ok_false_without_taking_down_the_fleet():
    jobs = [
        {"name": "boom", "workdir": "a", "task": "x"},
        {"name": "fine", "workdir": "b", "task": "x"},
    ]
    make_harness = make_harness_factory({
        "a": ("raise", ValueError("bad task")),
        "b": ("sleep_return", (0.0, "ok")),
    })

    results = fleet.run_fleet(jobs, make_harness, max_workers=2)

    assert results[0] == {"name": "boom", "ok": False, "report": "ValueError: bad task"}
    assert results[1] == {"name": "fine", "ok": True, "report": "ok"}


def test_empty_job_list_returns_empty_results():
    assert fleet.run_fleet([], make_harness_factory({})) == []
