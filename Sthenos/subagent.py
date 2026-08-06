"""Day 4 -- sub-agents: delegating a task to a fresh, isolated context.

A task that's self-contained -- "find every caller of this function",
"summarize this directory" -- doesn't need the parent conversation's
history to do it, and doing it inline spends the parent's context budget
on the child's intermediate tool calls for no benefit. spawn_agent hands
the task to a brand-new agent instead: its own clean messages list, its
own budget, and only the final report crosses back.

subagent_tool doesn't build that agent itself -- it takes make_harness,
a one-argument callable the caller supplies, and calls it with the next
depth down. That's the whole boundary: this module knows how to gate
recursion and how to shape the tool, not what a harness is made of.

Design rules:
  - depth is the only defense against infinite recursion. A sub-agent
    that could itself spawn sub-agents without a falling budget is a
    fork bomb with a system prompt; max_depth is checked before
    make_harness runs at all, not after.
  - the limit is a tool result, not an exception. The parent agent reads
    "do this task yourself" and can actually do that -- a raised error
    would just end its turn with nothing to act on.
"""

from .tools import tool


def subagent_tool(make_harness, depth=0, max_depth=2):
    """Build the spawn_agent tool, gated to at most max_depth levels of nesting."""

    @tool("Delegate a self-contained task to a fresh sub-agent with its own clean "
          "context. The child cannot see this conversation and only its final "
          "report comes back -- use this to offload independent work without "
          "spending this conversation's context on the child's intermediate steps.",
          task="The self-contained task for the child agent to carry out")
    def spawn_agent(task):
        if depth >= max_depth:
            return "ERROR: sub-agent depth limit reached; do this task yourself"
        child = make_harness(depth + 1)
        return child.run(task)

    return spawn_agent
