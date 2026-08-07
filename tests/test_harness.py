"""Tests for Sthenos.harness -- the day-5 Harness, without hitting the network.

Anything that would call provider.complete swaps it for a fake, same as
tests/test_context.py -- these check the wiring, not the model.
"""

import os
import tempfile
from contextlib import contextmanager

from Sthenos import context, harness, memory, provider, security, session, skills
from Sthenos.tools import tool


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


# --- construction / tool registry ------------------------------------------

def test_tools_are_the_six_core_tools_plus_remember_and_spawn_agent():
    h = harness.Harness(workdir())
    assert sorted(h.tools) == [
        "bash", "edit_file", "grep", "list_files", "read_file",
        "remember", "spawn_agent", "write_file",
    ]


def test_use_skill_only_appears_when_a_skill_exists():
    wd = workdir()
    assert "use_skill" not in harness.Harness(wd).tools

    skill_dir = os.path.join(wd, skills.SKILLS_DIR, "brief")
    os.makedirs(skill_dir)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\ndescription: keep it short\n---\nBe brief.")

    h = harness.Harness(wd)
    assert h.tools["use_skill"].run(name="brief") == skills.read_skill(wd, "brief")


def test_spawn_agent_absent_when_subagents_are_disabled():
    assert "spawn_agent" not in harness.Harness(workdir(), enable_subagents=False).tools


def test_extra_tools_are_merged_into_the_registry():
    @tool("says hi")
    def hello():
        return "hi"

    h = harness.Harness(workdir(), extra_tools={"hello": hello})
    assert h.tools["hello"].run() == "hi"


def test_remember_tool_writes_through_memory_remember():
    wd = workdir()
    harness.Harness(wd).tools["remember"].run(note="this repo uses Polars")
    with open(os.path.join(wd, memory.MEMORY_FILE), encoding="utf-8") as f:
        assert "this repo uses Polars" in f.read()


def test_system_prompt_folds_in_memory_skills_and_system_extra():
    wd = workdir()
    memory.remember(wd, "this repo uses Polars, not pandas")
    os.makedirs(os.path.join(wd, skills.SKILLS_DIR, "terse"))
    with open(os.path.join(wd, skills.SKILLS_DIR, "terse", "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\ndescription: answer in one line\n---\nBe terse.")

    h = harness.Harness(wd, system_extra="Ship it fast.")

    assert "this repo uses Polars, not pandas" in h.system
    assert "terse: answer in one line" in h.system
    assert "Ship it fast." in h.system


def test_model_defaults_to_the_env_var_then_the_provider_default():
    saved = os.environ.pop("sthenos_MODEL", None)
    try:
        assert harness.Harness(workdir()).model == provider.DEFAULT_MODEL
        os.environ["sthenos_MODEL"] = "claude-test-model"
        assert harness.Harness(workdir()).model == "claude-test-model"
    finally:
        if saved is None:
            os.environ.pop("sthenos_MODEL", None)
        else:
            os.environ["sthenos_MODEL"] = saved


# --- spawning children -------------------------------------------------------

def test_spawn_child_shares_workdir_and_policy_goes_one_level_deeper_and_is_ephemeral():
    wd = workdir()
    policy = security.Policy("read-only")
    h = harness.Harness(wd, model="model-x", policy=policy, budget_tokens=999, _depth=1)

    child = h._make_child(2)

    assert child.workdir == h.workdir
    assert child.policy is policy
    assert child.model == "model-x"
    assert child.budget_tokens == 999
    assert child._depth == 2
    assert child.persist is False


def test_spawn_agent_tool_refuses_at_the_default_depth_limit():
    h = harness.Harness(workdir(), _depth=2)
    assert h.tools["spawn_agent"].run(task="anything") == \
        "ERROR: sub-agent depth limit reached; do this task yourself"


# --- run() --------------------------------------------------------------------

def test_run_returns_the_models_final_answer():
    with fake_complete(text="the answer"):
        result = harness.Harness(workdir()).run("do the thing")
    assert result == "the answer"


def test_run_persists_the_task_and_reply_to_a_session_file():
    wd = workdir()
    with fake_complete(text="all done"):
        harness.Harness(wd).run("do the thing")
    path = session.latest(wd)
    assert path is not None
    assert session.load(path) == [
        {"role": "user", "text": "do the thing"},
        {"role": "assistant", "text": "all done", "tool_calls": []},
    ]


def test_run_does_not_persist_when_persist_is_false():
    wd = workdir()
    with fake_complete(text="all done"):
        harness.Harness(wd, persist=False).run("do the thing")
    assert session.latest(wd) is None


def test_session_label_is_the_first_32_chars_of_the_task():
    wd = workdir()
    with fake_complete(text="ok"):
        harness.Harness(wd).run("x" * 60)
    path = session.latest(wd)
    assert os.path.basename(path).endswith("-" + "x" * 32 + ".jsonl")


def test_resume_loads_a_past_session_and_run_appends_to_the_same_file():
    wd = workdir()
    with fake_complete(text="first"):
        h1 = harness.Harness(wd)
        h1.run("first task")
    first_path = h1.session_path

    with fake_complete(text="second"):
        h2 = harness.Harness(wd)
        assert h2.resume() is True
        h2.run("second task")

    assert h2.session_path == first_path
    assert session.load(first_path) == [
        {"role": "user", "text": "first task"},
        {"role": "assistant", "text": "first", "tool_calls": []},
        {"role": "user", "text": "second task"},
        {"role": "assistant", "text": "second", "tool_calls": []},
    ]


def test_resume_with_no_session_returns_false_and_leaves_messages_empty():
    h = harness.Harness(workdir())
    assert h.resume() is False
    assert h.messages == []


def test_a_shrinking_compaction_never_drops_a_message_from_the_session_file():
    """The file stays the full raw transcript even when self.messages gets summarized mid-run."""
    wd = workdir()
    turn = {"n": 0}

    def fake(model, system, messages, tools=None):
        turn["n"] += 1
        if turn["n"] == 1:
            return {"text": "", "tool_calls": [{"name": "list_files", "args": {}}],
                    "usage": {"input": 0, "output": 0}}
        return {"text": "final", "tool_calls": [], "usage": {"input": 0, "output": 0}}

    def shrink_after_first_turn(model, messages, budget_tokens):
        if len(messages) <= 1:
            return messages
        return [{"role": "user", "text": "[compacted]"}] + messages[-1:]

    original_complete, original_compact = provider.complete, context.compact
    provider.complete, context.compact = fake, shrink_after_first_turn
    try:
        h = harness.Harness(wd)
        result = h.run("go")
    finally:
        provider.complete, context.compact = original_complete, original_compact

    assert result == "final"
    recorded = session.load(session.latest(wd))
    assert recorded[0] == {"role": "user", "text": "go"}
    assert recorded[-1] == {"role": "assistant", "text": "final", "tool_calls": []}
    assert any(m.get("name") == "list_files" for m in recorded if m["role"] == "tool")
    assert not any("[compacted]" in m.get("text", "") for m in recorded)
    assert h._recorded == len(h.messages)
