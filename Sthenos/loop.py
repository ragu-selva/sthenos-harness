"""Day 1 -- the turn loop.

This is the whole agent: ask the model, act on what it asks for, repeat.
Everything else in the harness (security gates, memory, subagents) plugs
into the two hooks here -- before_tool and before_turn -- rather than
this function growing new branches for each concern. That's the point of
having a loop module at all: policy and mechanism stay separate.

Design rules:
  - the loop never crashes because a tool did. An unknown tool name or a
    raised exception becomes an ERROR string the model reads as a result,
    not a Python traceback that kills the session.
  - before_tool is a pure yes/no gate, decided before the tool runs; it
    never sees or changes the result. Whatever enforces policy (day 5's
    security.py) plugs in here without this file knowing what "policy" means.
  - before_turn is unused today -- it exists so day 3 can compact the
    message list before it grows unbounded, without changing this
    function's shape.
"""

from . import provider


def run_loop(model, system, messages, tools, on_event, before_tool,
             max_turns=80, before_turn=None):
    """Drive assistant/tool turns until the model answers without calling a tool.

    tools maps name -> Tool, an object with .spec ({"schema": ...}) and
    .run(**kwargs). Returns the model's final answer text.
    """
    specs = [t.spec for t in tools.values()]
    for _ in range(max_turns):
        if before_turn is not None:
            messages = before_turn(messages)
        reply = provider.complete(model, system, messages, specs)
        messages.append({"role": "assistant", "text": reply["text"], "tool_calls": reply["tool_calls"]})
        on_event("assistant", reply)
        if not reply["tool_calls"]:
            return reply["text"]
        for call in reply["tool_calls"]:
            result = _run_tool(call, tools, before_tool, on_event)
            messages.append({"role": "tool", "name": call["name"], "text": str(result)})

    messages.append({"role": "user", "text": "Turn limit reached; wrap up now."})
    reply = provider.complete(model, system, messages, [])
    messages.append({"role": "assistant", "text": reply["text"], "tool_calls": reply["tool_calls"]})
    on_event("assistant", reply)
    return reply["text"]


def _run_tool(call, tools, before_tool, on_event):
    """Run one tool call under the before_tool gate, turning failures into text.

    A blocked or failed call still returns a result string -- the loop
    keeps going so the model can see what happened and adapt.
    """
    name = call["name"]
    on_event("tool_start", call)
    if name not in tools:
        result = f"ERROR: unknown tool {name}"
    else:
        reason = before_tool(call)
        if reason is not None:
            result = f"BLOCKED: {reason}"
        else:
            try:
                result = tools[name].run(**call["args"])
            except Exception as e:
                result = f"ERROR: {type(e).__name__}: {e}"
    on_event("tool_end", {"name": name, "result": result})
    return result
