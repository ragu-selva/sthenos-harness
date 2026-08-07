"""Day 5 -- the spine, rebuilt: one object a caller constructs once and runs many times.

Day 4's Harness rebuilt its tool registry and system prompt on every run()
call, because nothing yet needed a Harness to outlive a single task. Day 5
does: the CLI keeps one Harness alive across an interactive session, fleet.py
hands many jobs to many harnesses, and spawn_agent needs a child that shares
its parent's workdir and policy but keeps its own, disposable session. That
means construction has to do the real work -- tools, system prompt, policy --
once, and run() has to be safe to call more than once against messages that
may already hold a resumed conversation.

Design rules:
  - construction is where the wiring happens. tools, system prompt, and the
    subagent factory are built in __init__ and read off self from then on;
    run() only ever adds to what's already there.
  - messages is the one true conversation. resume() loads it from disk;
    run() appends to it and hands it to run_loop. Compaction (before_turn)
    can replace it wholesale with a summary, and self.messages is kept
    pointing at whatever run_loop is actually using -- see _flush.
  - the session file is a raw log, not a cache of self.messages. Every
    message is appended the moment it's confirmed to exist, before
    compaction ever gets a chance to summarize it away; a compacted
    self.messages is smaller, but the file on disk never loses a turn.
  - a spawned child is ephemeral by construction. persist=False is not a
    run()-time choice -- a child that could resume would let a sub-agent's
    throwaway session shadow the parent's --resume, so the constructor is
    the only place that decides it.
"""

import os

from . import context, loop, memory, provider, security, session, skills, subagent
from .tools import core_tools, tool

DEFAULT_BUDGET_TOKENS = 600_000
DEFAULT_MAX_TURNS = 120


class Harness:
    """One agent: tools, policy, memory, skills, compaction, and a session log, wired once."""

    def __init__(self, workdir=".", model=None, policy=None, extra_tools=None,
                 system_extra="", on_event=None, budget_tokens=DEFAULT_BUDGET_TOKENS,
                 max_turns=DEFAULT_MAX_TURNS, session_path=None, enable_subagents=True,
                 persist=True, _depth=0):
        self.workdir = os.path.realpath(workdir)
        os.makedirs(self.workdir, exist_ok=True)
        self.model = model or os.environ.get("sthenos_MODEL") or provider.DEFAULT_MODEL
        self.policy = policy or security.Policy("yolo")
        self.system_extra = system_extra
        self.on_event = on_event or (lambda kind, payload: None)
        self.budget_tokens = budget_tokens
        self.max_turns = max_turns
        self.session_path = session_path
        self.enable_subagents = enable_subagents
        self.persist = persist
        self._depth = _depth

        self.tools = {t.name: t for t in core_tools(self.workdir)}
        self.tools["remember"] = _remember_tool(self.workdir)
        if skills.catalog(self.workdir):
            self.tools["use_skill"] = _use_skill_tool(self.workdir)
        if enable_subagents:
            self.tools["spawn_agent"] = subagent.subagent_tool(self._make_child, self._depth)
        if extra_tools:
            self.tools.update(extra_tools)

        extra = "\n\n".join(part for part in (skills.catalog_prompt(self.workdir), system_extra) if part)
        self.system = memory.build_system_prompt(self.workdir, extra=extra)

        self.messages = []
        self._recorded = 0

    def resume(self, path=None):
        """Load a past session's messages back in. Returns True when there was one to load."""
        path = path or session.latest(self.workdir)
        if not path:
            return False
        messages = session.load(path)
        if not messages:
            return False
        self.messages = messages
        self.session_path = path
        self._recorded = len(messages)
        return True

    def run(self, task):
        """Run task to completion, appending to whatever conversation already exists."""
        if self.persist and not self.session_path:
            self.session_path = session.new_session(self.workdir, task[:32])

        self.messages.append({"role": "user", "text": task})
        self._flush()

        def before_turn(messages):
            # Flush before compacting, not after: a tool result lands in
            # messages after its own tool_end event fires (see loop.run_loop),
            # so the only guaranteed checkpoint before compaction might
            # summarize it away is the top of the next turn.
            self.messages = messages
            self._flush()
            messages = context.compact(self.model, self.messages, self.budget_tokens)
            self.messages = messages
            self._recorded = min(self._recorded, len(messages))
            return messages

        def tracked_event(kind, payload):
            self._flush()
            self.on_event(kind, payload)

        try:
            return loop.run_loop(self.model, self.system, self.messages, self.tools,
                                  tracked_event, self.policy.check,
                                  max_turns=self.max_turns, before_turn=before_turn)
        finally:
            self._flush()

    def _flush(self):
        """Append every message landed since the last flush to the session file.

        Indexed off self.messages rather than the event payload, so a
        compaction that just shrank the list is caught by clamping
        _recorded down to the new length instead of slicing past the end.
        """
        if not self.persist:
            return
        self._recorded = min(self._recorded, len(self.messages))
        for msg in self.messages[self._recorded:]:
            session.append(self.session_path, msg)
        self._recorded = len(self.messages)

    def _make_child(self, depth):
        """Build the sub-agent for spawn_agent: same workdir and policy, one level deeper, ephemeral."""
        return Harness(self.workdir, model=self.model, policy=self.policy,
                        system_extra=self.system_extra, on_event=self.on_event,
                        budget_tokens=self.budget_tokens, max_turns=self.max_turns,
                        enable_subagents=self.enable_subagents, persist=False, _depth=depth)


def _remember_tool(workdir):
    """The remember tool: wraps memory.remember so the model can note things worth keeping."""

    @tool("Append a durable note to this project's memory, so future runs over this "
          "directory start already knowing it. Use it for facts worth keeping, not "
          "task-specific chatter.",
          note="The note to remember, as a short factual sentence")
    def remember(note):
        return memory.remember(workdir, note)

    return remember


def _use_skill_tool(workdir):
    """The use_skill tool: reads skills.read_skill so skills.py stays plain file I/O."""

    @tool("Load a skill's full instructions by name. See the skill catalog in the "
          "system prompt for what's available and when each one applies.",
          name="The skill's name, exactly as it appears in the catalog")
    def use_skill(name):
        return skills.read_skill(workdir, name)

    return use_skill
