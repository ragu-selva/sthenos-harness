"""Tests for Sthenos.harness -- the composed Harness, without hitting the network.

Anything that would call provider.complete swaps it for a fake, same as
tests/test_context.py -- this file checks the wiring, not the model.
"""

import os
import tempfile
from contextlib import contextmanager

from Sthenos import harness, memory, provider, session, skills


def workdir():
    return tempfile.mkdtemp(prefix="sthenos_test_")


@contextmanager
def fake_complete(text="done", tool_calls=None, calls=None):
    original = provider.complete

    def fake(model, system, messages, tools=None):
        if calls is not None:
            calls.append({"model": model, "system": system, "messages": messages})
        return {"text": text, "tool_calls": tool_calls or [], "usage": {"input": 0, "output": 0}}

    provider.complete = fake
    try:
        yield
    finally:
        provider.complete = original


# --- the tool registry ---------------------------------------------------

def test_registry_has_the_six_core_tools_plus_use_skill_and_spawn_agent():
    h = harness.Harness(workdir())
    assert sorted(h._registry()) == [
        "bash", "edit_file", "grep", "list_files", "read_file",
        "spawn_agent", "use_skill", "write_file",
    ]


def test_use_skill_tool_reads_through_skills_read_skill():
    wd = workdir()
    skill_dir = os.path.join(wd, skills.SKILLS_DIR, "brief")
    os.makedirs(skill_dir)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\ndescription: keep it short\n---\nBe brief.")
    h = harness.Harness(wd)
    assert h._registry()["use_skill"].run(name="brief") == skills.read_skill(wd, "brief")


def test_use_skill_tool_reports_a_miss_the_same_way_skills_does():
    wd = workdir()
    h = harness.Harness(wd)
    assert h._registry()["use_skill"].run(name="nope") == skills.read_skill(wd, "nope")


# --- spawning children -----------------------------------------------------

def test_spawn_child_goes_one_level_deeper_and_keeps_the_rest():
    wd = workdir()
    h = harness.Harness(wd, model="model-x", mode="read-only", budget_tokens=999,
                         depth=1, max_depth=5)
    child = h._spawn_child(2)
    assert child.workdir == wd
    assert child.model == "model-x"
    assert child.policy.mode == "read-only"
    assert child.budget_tokens == 999
    assert child.depth == 2
    assert child.max_depth == 5
    assert child.session_label == "subagent"


def test_spawn_agent_tool_refuses_at_the_depth_limit_without_a_child_harness():
    h = harness.Harness(workdir(), depth=2, max_depth=2)
    result = h._registry()["spawn_agent"].run(task="anything")
    assert result == "ERROR: sub-agent depth limit reached; do this task yourself"


# --- run() ----------------------------------------------------------------

def test_run_returns_the_models_final_answer():
    with fake_complete(text="the answer"):
        result = harness.Harness(workdir()).run("do the thing")
    assert result == "the answer"


def test_run_logs_the_task_and_the_reply_to_a_session_file():
    wd = workdir()
    with fake_complete(text="all done"):
        harness.Harness(wd).run("do the thing")
    path = session.latest(wd)
    assert path is not None
    assert session.load(path) == [
        {"role": "user", "text": "do the thing"},
        {"role": "assistant", "text": "all done", "tool_calls": []},
    ]


def test_run_builds_the_system_prompt_from_memory_and_skills():
    wd = workdir()
    memory.remember(wd, "this repo uses Polars, not pandas")
    os.makedirs(os.path.join(wd, skills.SKILLS_DIR, "terse"))
    with open(os.path.join(wd, skills.SKILLS_DIR, "terse", "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\ndescription: answer in one line\n---\nBe terse.")

    calls = []
    with fake_complete(calls=calls):
        harness.Harness(wd).run("go")

    system = calls[0]["system"]
    assert "this repo uses Polars, not pandas" in system
    assert "terse: answer in one line" in system
