"""Tests for Sthenos.subagent -- the spawn_agent tool and its depth gate."""

from Sthenos import subagent


class FakeChild:
    """Stands in for a Harness: records the task it was given, returns a fixed report."""

    def __init__(self, report="child report"):
        self.report = report
        self.tasks = []

    def run(self, task):
        self.tasks.append(task)
        return self.report


def make_harness_factory(children_by_depth):
    """A make_harness that hands back a pre-built FakeChild for the requested depth."""
    calls = []

    def make_harness(depth):
        calls.append(depth)
        return children_by_depth[depth]

    return make_harness, calls


# --- the schema ----------------------------------------------------------

def test_the_tool_is_named_spawn_agent_with_one_required_parameter():
    tool = subagent.subagent_tool(lambda depth: FakeChild())
    schema = tool.spec["schema"]
    assert schema["name"] == "spawn_agent"
    assert schema["parameters"]["required"] == ["task"]


# --- delegating -------------------------------------------------------

def test_below_the_depth_limit_delegates_to_a_child_built_at_depth_plus_one():
    child = FakeChild(report="done: found 3 callers")
    make_harness, calls = make_harness_factory({1: child})
    tool = subagent.subagent_tool(make_harness, depth=0, max_depth=2)

    result = tool.run(task="find callers of foo()")

    assert calls == [1]
    assert child.tasks == ["find callers of foo()"]
    assert result == "done: found 3 callers"


def test_depth_is_threaded_through_on_each_call():
    child = FakeChild()
    make_harness, calls = make_harness_factory({4: child})
    tool = subagent.subagent_tool(make_harness, depth=3, max_depth=5)

    tool.run(task="x")

    assert calls == [4]


# --- the depth gate -----------------------------------------------------

def test_at_the_depth_limit_refuses_without_calling_make_harness():
    make_harness, calls = make_harness_factory({})
    tool = subagent.subagent_tool(make_harness, depth=2, max_depth=2)

    result = tool.run(task="anything")

    assert result == "ERROR: sub-agent depth limit reached; do this task yourself"
    assert calls == []


def test_past_the_depth_limit_also_refuses():
    make_harness, calls = make_harness_factory({})
    tool = subagent.subagent_tool(make_harness, depth=5, max_depth=2)

    assert tool.run(task="anything") == "ERROR: sub-agent depth limit reached; do this task yourself"
    assert calls == []


def test_default_depth_and_max_depth_allow_two_levels_of_nesting():
    child = FakeChild()
    make_harness, calls = make_harness_factory({1: child})
    tool = subagent.subagent_tool(make_harness)  # depth=0, max_depth=2

    tool.run(task="x")

    assert calls == [1]
