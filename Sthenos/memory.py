"""Day 3 -- durable memory: what the agent knows before the first message.

Everything so far lives and dies with one conversation. STHENOS.md is the
fix: a plain markdown file in the working directory that build_system_prompt
folds into the system prompt on every run, and remember() appends to. A
fresh conversation over the same directory starts already knowing what a
past one learned -- no vector store, no retrieval step, just a file the
agent can read because it's sitting right there in the prompt.

Design rules:
  - memory is a file, not a service. Grep it, edit it by hand, delete a
    line that turned out wrong -- anything that works on a markdown file
    works on the agent's memory, including tools this module never heard of.
  - the system prompt is assembled once per run, not maintained. There is
    no cache to invalidate and no update path other than remember() plus
    whatever the file looks like the next time build_system_prompt runs.
  - remember() only appends. A tool that could also edit or delete lines
    is a tool that can quietly erase what a past run decided was worth
    keeping; overwriting STHENOS.md is a job for a text editor, not this API.
"""

import os
import platform

MEMORY_FILE = "STHENOS.md"

BASE_PROMPT = (
    "You are Sthenos, a small, sharp coding agent working inside one directory "
    "with the tools you've been given. Act, don't narrate -- do the work with "
    "tools rather than describing what you would do. Inspect before assuming: "
    "read a file or list a directory before relying on what's in it. Prefer "
    "edit_file over write_file for small changes -- rewriting a whole file to "
    "change one line risks losing the rest of it. Verify after building by "
    "running what you wrote or re-reading it; a tool call that succeeded "
    "silently is not the same as one that did what you meant. Never repeat a "
    "failing call unchanged -- if it failed once, change something before "
    "trying again. When the task is complete, reply with a short summary and "
    "stop calling tools."
)


def build_system_prompt(workdir, extra=""):
    """Assemble the system prompt: base rules, platform/workdir, project memory, extra.

    Each part is optional past the first two -- STHENOS.md may not exist
    yet, and extra is only there when a caller (a skill catalog, a task-
    specific instruction) has something to add. Parts are joined by blank
    lines so the model reads distinct sections, not one run-on paragraph.
    """
    real_workdir = os.path.realpath(workdir)
    parts = [BASE_PROMPT, f"Platform: {platform.system()}. Working directory: {real_workdir}."]

    memory_path = os.path.join(workdir, MEMORY_FILE)
    if os.path.isfile(memory_path):
        with open(memory_path, encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            parts.append(f"Project memory (sthenos.md):\n{content}")

    if extra:
        parts.append(extra)

    return "\n\n".join(parts)


def remember(workdir, note):
    """Append note as a bullet to STHENOS.md, creating the file if needed."""
    memory_path = os.path.join(workdir, MEMORY_FILE)
    with open(memory_path, "a", encoding="utf-8") as f:
        f.write(f"- {note}\n")
    return "Remembered in sthenos.md"
