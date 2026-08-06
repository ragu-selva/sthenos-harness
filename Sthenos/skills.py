"""Day 3 -- skills: instructions the agent loads only when they're relevant.

Stuffing every specialized instruction into the system prompt punishes
every task with the token cost of all of them. A skill is one markdown
file the agent reads on demand instead: catalog_prompt tells it what
exists and its one-line purpose, and the use_skill tool (built where the
tool registry is assembled, not here -- see harness.py) hands back the
full file only when the model decides a task needs it.

Design rules:
  - a skill is a file, not a plugin. skills/<name>/SKILL.md is markdown
    like STHENOS.md; writing one is authoring, not coding, and this
    module changes zero code paths when a skill's instructions change.
  - the catalog is cheap on purpose. It reads the front matter of every
    SKILL.md up front so build_system_prompt can list what's available
    without the cost of the full files; the full text only gets read
    when read_skill is actually called for that one skill.
  - a missing skill is a tool result, not an exception. The model asked
    for a name that doesn't exist; it should see what does, not a
    traceback -- same reasoning as tools.py's own failure strings.
"""

import os

SKILLS_DIR = "skills"


def catalog(workdir):
    """Map skill name -> {"description", "path"} for every skills/<name>/SKILL.md.

    A directory under skills/ with no SKILL.md in it isn't a skill --
    skipped rather than reported as a broken one.
    """
    root = os.path.join(workdir, SKILLS_DIR)
    found = {}
    if not os.path.isdir(root):
        return found
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name, "SKILL.md")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        found[name] = {"description": _front_matter_description(text), "path": path}
    return found


def catalog_prompt(workdir):
    """Render the catalog as a system-prompt section, or "" when there are no skills."""
    skills = catalog(workdir)
    if not skills:
        return ""
    lines = ["Skills available (load one with the use_skill tool when relevant):"]
    lines += [f"- {name}: {skills[name]['description']}" for name in sorted(skills)]
    return "\n".join(lines)


def read_skill(workdir, name):
    """Return the full SKILL.md text for name, or an error string naming what exists."""
    skills = catalog(workdir)
    if name not in skills:
        available = ", ".join(sorted(skills)) or "(none)"
        return f"ERROR: no skill named {name}. Available: {available}"
    with open(skills[name]["path"], encoding="utf-8") as f:
        return f.read()


def _front_matter_description(text):
    """Pull the description: line out of a leading '---' front-matter block, if any."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if stripped.startswith("description:"):
            return stripped.split(":", 1)[1].strip().strip("\"'")
    return ""
