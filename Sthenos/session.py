"""Day 4 -- durable sessions: a conversation that survives the process dying.

messages has lived in memory alone through every prior day; a crash mid-
run loses the whole transcript with it. append() makes each message
durable the moment the loop adds it -- one JSON line, flushed on close --
so load() can hand the exact conversation back to a fresh process.

The one failure mode worth naming: a crash lands mid-write only at the
very end of the file, never in the middle, and it lands mid-*turn*, not
mid-message -- a tool call gets sent to the model, the process dies
before every result comes back. load()'s repair exists for exactly that
shape of damage; nothing else needs handling.

Design rules:
  - append per message, not per turn. A turn can raise a tool_calls list
    without its tool results yet; buffering to write once loses whatever
    was true right before the crash, which is the one moment durability
    is actually for.
  - a torn last line is data, not an error. fsync isn't in scope here, so
    the last line of a session file killed mid-write is exactly the
    corruption to expect, not a sign the file is unusable -- keep every
    line before it and move on.
  - repair restores a valid call/response pairing, not the true outcome.
    "Interrupted before this ran" is an honest placeholder, not a guess
    at what the tool would have returned -- the provider requires every
    tool_use to have a tool_result; this is the only truthful one to give it.
"""

import json
import os
import re
import time

SESSION_DIR = ".sthenos/sessions"

_INTERRUPTED = "Interrupted before this ran (process restarted)."


def _session_root(workdir):
    return os.path.join(workdir, *SESSION_DIR.split("/"))


def _slugify(label):
    """Alphanumerics and dashes only, collapsed and clipped to 40 chars."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", label).strip("-")
    return (slug or "session")[:40]


def new_session(workdir, label="session"):
    """Create the session directory and return a fresh timestamped path for it."""
    root = _session_root(workdir)
    os.makedirs(root, exist_ok=True)
    filename = f"{int(time.time())}-{_slugify(label)}.jsonl"
    return os.path.join(root, filename)


def append(path, message):
    """Append one message to the session file as a single JSON line."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(message, ensure_ascii=False) + "\n")


def load(path):
    """Read a session file back into a message list, repairing a torn tail.

    A line that fails to parse is where a crash cut the file off
    mid-write; everything before it is a complete message and everything
    from it on is discarded, not just skipped.
    """
    messages = []
    if not os.path.isfile(path):
        return messages
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                break
    return _repair(messages)


def latest(workdir):
    """Return the newest session file's path, or None if there isn't one."""
    root = _session_root(workdir)
    if not os.path.isdir(root):
        return None
    files = sorted(f for f in os.listdir(root) if f.endswith(".jsonl"))
    return os.path.join(root, files[-1]) if files else None


def _repair(messages):
    """Backfill a tool_result for any tool_call the crash cut off before it answered.

    Finds the last assistant message, counts the tool messages that
    already answer it, and synthesizes the rest -- so the list always
    satisfies the one-tool_result-per-tool_call rule the provider needs,
    even when the process died between two of them.
    """
    last_assistant = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "assistant":
            last_assistant = i
            break
    if last_assistant is None:
        return messages

    tool_calls = messages[last_assistant].get("tool_calls") or []
    answered = sum(1 for m in messages[last_assistant + 1:] if m.get("role") == "tool")
    for call in tool_calls[answered:]:
        messages.append({"role": "tool", "name": call["name"], "text": _INTERRUPTED})
    return messages
