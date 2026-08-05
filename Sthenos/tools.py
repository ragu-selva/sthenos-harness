"""Day 2 -- tools the model can actually call.

Day 1 hand-wrote a tool: a class with a .spec dict typed out by hand and
a .run method. That does not scale past one tool -- the schema and the
function drift apart the moment either changes. This file fixes that in
two halves. tool() derives the schema from the function signature, so
the description of a tool and the tool itself cannot disagree. Then
core_tools() supplies the six that every coding agent needs, closed over
a working directory none of them can escape.

Design rules:
  - a Tool is data, not a base class. name/spec/run, nothing to inherit
    and nothing to override; run_loop already accepts anything with
    .spec and .run, so this stays compatible with day 1's hand-written
    tool without either knowing about the other.
  - every parameter is a string. Models emit "3" and 3 interchangeably
    and JSON-schema number types make that a validation error instead of
    a value; taking strings and converting inside the tool moves the
    problem to the one place that knows what the argument means.
  - exactly one resolve(). A path check that appears twice is a path
    check that will be forgotten once, so every tool that touches the
    filesystem goes through it and it raises rather than returns -- an
    ignored return value is silent, an ignored exception is not.
  - tools return strings the model reads, including their failures. A
    tool that cannot do the thing explains why in the result; run_loop
    catches what escapes and does the same. The model gets a sentence it
    can act on, never a traceback and never silence.
"""

import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass
from inspect import Parameter, signature
from typing import Callable

MAX_READ_LINES = 4000
MAX_BASH_CHARS = 12000
MAX_LIST_ENTRIES = 500
MAX_GREP_HITS = 200
MAX_GREP_LINE = 200

# Directories that are always noise in a source tree: huge, generated,
# and never what someone means by "search the project".
IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv"}


@dataclass
class Tool:
    """One callable tool: its name, the schema the provider sends, and the function."""

    name: str
    spec: dict
    run: Callable


def tool(description, **params):
    """Turn a plain function into a Tool, deriving its schema from the signature.

    params maps each argument name to the description the model reads.
    Arguments with defaults are optional; the rest are required. Every
    argument is typed string -- see the module docstring.
    """
    def decorate(fn):
        args = signature(fn).parameters
        return Tool(
            name=fn.__name__,
            spec={"schema": {
                "name": fn.__name__,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        name: {"type": "string", "description": params.get(name, "")}
                        for name in args
                    },
                    "required": [name for name, p in args.items()
                                 if p.default is Parameter.empty],
                },
            }},
            run=fn,
        )
    return decorate


def _matches(rel, name, pattern):
    """True if pattern matches the relative path or the basename.

    A leading '**/' is also tried stripped. fnmatch has no notion of
    '**' -- it expands every '*' to "any characters", so '**/*' would
    require at least one separator and silently miss every top-level
    file, which is the default pattern's whole job.
    """
    candidates = [pattern, pattern[3:]] if pattern.startswith("**/") else [pattern]
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) for p in candidates)


def core_tools(workdir):
    """Build the six core tools, each confined to workdir. Returns a list of Tool."""
    root = os.path.realpath(workdir)

    def resolve(path):
        """Map a caller-supplied path into workdir, or raise if it points outside.

        realpath first, so '..' and symlinks are already collapsed --
        comparing the literal string would let either walk straight out.
        """
        full = os.path.realpath(os.path.join(root, path))
        if full != root and not full.startswith(root + os.sep):
            raise PermissionError(f"{path!r} escapes the working directory")
        return full

    def walk():
        """Yield every file under root, skipping the directories nobody means to search."""
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
            for name in filenames:
                yield os.path.join(dirpath, name)

    def relative(full):
        """Path relative to root, with forward slashes so patterns behave the same everywhere."""
        return os.path.relpath(full, root).replace(os.sep, "/")

    @tool("Read a file, with line numbers",
          path="File to read, relative to the working directory")
    def read_file(path):
        with open(resolve(path), encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        body = "\n".join(f"{i}\t{line}" for i, line in enumerate(lines[:MAX_READ_LINES], 1))
        if len(lines) > MAX_READ_LINES:
            body += f"\n... truncated: showing {MAX_READ_LINES} of {len(lines)} lines"
        return body

    @tool("Write a file, creating parent directories as needed",
          path="File to write, relative to the working directory",
          content="Full contents to write; replaces the file entirely")
    def write_file(path, content):
        full = resolve(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Wrote {len(content)} chars to {path}"

    @tool("Replace an exact snippet in a file; the snippet must appear exactly once",
          path="File to edit, relative to the working directory",
          old="Exact text to replace, copied from the file",
          new="Text to put in its place")
    def edit_file(path, old, new):
        full = resolve(path)
        with open(full, encoding="utf-8") as f:
            text = f.read()
        # Uniqueness is the whole safety property here: an ambiguous
        # snippet edited anyway is a silent wrong edit, so refuse and say
        # what would fix it.
        found = text.count(old)
        if found == 0:
            return "ERROR: snippet not found — read the file and copy it exactly"
        if found > 1:
            return f"ERROR: snippet appears {found} times — include more context to make it unique"
        with open(full, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new, 1))
        return f"Edited {path}"

    @tool("Run a shell command in the working directory",
          command="Shell command to run",
          timeout="Seconds to wait before giving up (default 120)")
    def bash(command, timeout="120"):
        seconds = int(timeout)
        try:
            done = subprocess.run(command, shell=True, cwd=root, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace",
                                  timeout=seconds)
        except subprocess.TimeoutExpired:
            return f"ERROR: timed out after {seconds}s"
        output = (done.stdout or "") + (done.stderr or "")
        if len(output) > MAX_BASH_CHARS:
            half = MAX_BASH_CHARS // 2
            cut = len(output) - MAX_BASH_CHARS
            output = f"{output[:half]}\n... {cut} characters truncated ...\n{output[-half:]}"
        # An exit code with no output is still information -- "nothing
        # happened" and "it printed nothing" look identical otherwise.
        return output or f"(exit {done.returncode}, no output)"

    @tool("List files in the working directory matching a glob",
          pattern="Glob to match, e.g. '**/*.py' (default '**/*')")
    def list_files(pattern="**/*"):
        hits = sorted(rel for rel in map(relative, walk())
                      if _matches(rel, os.path.basename(rel), pattern))
        if len(hits) > MAX_LIST_ENTRIES:
            return "\n".join(hits[:MAX_LIST_ENTRIES]) + \
                f"\n... and {len(hits) - MAX_LIST_ENTRIES} more"
        return "\n".join(hits) or f"(no files matching {pattern})"

    @tool("Search file contents for a regular expression",
          regex="Regular expression to search for",
          pattern="Glob limiting which files are searched (default '*')")
    def grep(regex, pattern="*"):
        compiled = re.compile(regex)
        hits = []
        for full in walk():
            rel = relative(full)
            if not _matches(rel, os.path.basename(rel), pattern):
                continue
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if compiled.search(line):
                            hits.append(f"{rel}:{lineno}: {line.rstrip()[:MAX_GREP_LINE]}")
                            if len(hits) >= MAX_GREP_HITS:
                                return "\n".join(hits) + \
                                    f"\n... stopped at {MAX_GREP_HITS} matches"
            except OSError:  # unreadable file is a skip, not a failed search
                continue
        return "\n".join(hits) or f"(no matches for {regex})"

    return [read_file, write_file, edit_file, bash, list_files, grep]
