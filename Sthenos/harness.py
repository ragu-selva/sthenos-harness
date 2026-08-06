"""Day 4 -- the spine: everything the week built, composed into one object.

No day handed this file an exact contract the way context.py, memory.py,
skills.py, session.py, and subagent.py each got one. It exists because
two things are otherwise true: subagent.subagent_tool needs a
make_harness(depth) callable that returns something with .run(task), and
every demo from here on would otherwise hand-wire the same dozen lines
-- tools plus use_skill plus spawn_agent, the memory-backed system
prompt, a session file, before_turn -- to get one working agent. Harness
is that wiring, done once. It invents no new policy; every decision
(what's a tool, what's allowed, when to compact, what's remembered) still
belongs to the module that owns it.

Design rules:
  - construction takes options, run() takes the task. Depth and the
    policy's mode are set once per agent, not re-decided per call, so a
    sub-agent spawned mid-run inherits its parent's settings by
    construction rather than by threading them through every call.
  - one session file per run() call. A sub-agent's transcript is its own
    file, not interleaved into its parent's -- session.latest() finding
    "the" session for a directory should mean something.
  - the tool registry is rebuilt per run(), not cached on the instance.
    skills/ and STHENOS.md can change between calls on a long-lived
    Harness; nothing here should require reconstructing the object to
    see that.
"""

from . import context, loop, memory, provider, security, session, skills, subagent
from .tools import core_tools, tool

DEFAULT_BUDGET_TOKENS = 8000
DEFAULT_MAX_DEPTH = 2


class Harness:
    """One agent, fully wired: tools, policy, memory, skills, compaction, a session log."""

    def __init__(self, workdir, model=None, mode="yolo", approver=None,
                 budget_tokens=DEFAULT_BUDGET_TOKENS, depth=0, max_depth=DEFAULT_MAX_DEPTH,
                 session_label="session", on_event=None):
        self.workdir = workdir
        self.model = model or provider.DEFAULT_MODEL
        self.policy = security.Policy(mode, approver=approver)
        self.budget_tokens = budget_tokens
        self.depth = depth
        self.max_depth = max_depth
        self.session_label = session_label
        self.on_event = on_event or (lambda kind, payload: None)

    def run(self, task):
        """Run task to completion in a fresh conversation; return the final answer."""
        registry = self._registry()
        system = memory.build_system_prompt(self.workdir, extra=skills.catalog_prompt(self.workdir))
        session_path = session.new_session(self.workdir, self.session_label)
        messages = [{"role": "user", "text": task}]
        session.append(session_path, messages[0])

        def before_turn(msgs):
            return context.compact(self.model, msgs, self.budget_tokens)

        def tracked_event(kind, payload):
            # The session log mirrors what the loop appends to messages, kept
            # here rather than in loop.py so a plain run_loop call never pays
            # for durability it didn't ask for.
            if kind == "assistant":
                session.append(session_path, {"role": "assistant", "text": payload["text"],
                                               "tool_calls": payload["tool_calls"]})
            elif kind == "tool_end":
                session.append(session_path, {"role": "tool", "name": payload["name"],
                                               "text": str(payload["result"])})
            self.on_event(kind, payload)

        return loop.run_loop(self.model, system, messages, registry, tracked_event,
                              self.policy.check, before_turn=before_turn)

    def _registry(self):
        registry = {t.name: t for t in core_tools(self.workdir)}
        registry["use_skill"] = _use_skill_tool(self.workdir)
        registry["spawn_agent"] = subagent.subagent_tool(self._spawn_child, self.depth, self.max_depth)
        return registry

    def _spawn_child(self, depth):
        """Build the sub-agent for spawn_agent: same settings, one level deeper."""
        return Harness(self.workdir, model=self.model, mode=self.policy.mode,
                        approver=self.policy.approver, budget_tokens=self.budget_tokens,
                        depth=depth, max_depth=self.max_depth, session_label="subagent",
                        on_event=self.on_event)


def _use_skill_tool(workdir):
    """The use_skill tool: reads skills.read_skill so skills.py stays plain file I/O."""

    @tool("Load a skill's full instructions by name. See the skill catalog in the "
          "system prompt for what's available and when each one applies.",
          name="The skill's name, exactly as it appears in the catalog")
    def use_skill(name):
        return skills.read_skill(workdir, name)

    return use_skill
