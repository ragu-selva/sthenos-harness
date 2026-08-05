"""Tests for Sthenos.tools -- schema generation, the sandbox, and the six tools."""

import os
import tempfile

from Sthenos import tools


def registry():
    """A fresh temp working directory with the six core tools bound to it."""
    workdir = tempfile.mkdtemp(prefix="sthenos_test_")
    return {t.name: t for t in tools.core_tools(workdir)}, workdir


def sleep_command(seconds):
    """A command that blocks for roughly seconds, in whichever shell bash() uses."""
    return f"ping -n {seconds + 1} 127.0.0.1 >nul" if os.name == "nt" else f"sleep {seconds}"


def print_file_command(name):
    """A command that dumps a file to stdout, in whichever shell bash() uses."""
    return f"type {name}" if os.name == "nt" else f"cat {name}"


# --- the decorator ---------------------------------------------------

def test_schema_name_comes_from_the_function():
    reg, _ = registry()
    assert reg["bash"].spec["schema"]["name"] == "bash"


def test_arguments_with_defaults_are_optional():
    """timeout has a default and command does not, so only command is required."""
    reg, _ = registry()
    assert reg["bash"].spec["schema"]["parameters"]["required"] == ["command"]
    assert reg["edit_file"].spec["schema"]["parameters"]["required"] == ["path", "old", "new"]


def test_every_parameter_is_string_typed():
    """Deliberate: models emit "3" and 3 interchangeably -- see the tools docstring."""
    reg, _ = registry()
    for tool in reg.values():
        for prop in tool.spec["schema"]["parameters"]["properties"].values():
            assert prop["type"] == "string"


def test_every_parameter_is_described():
    """An undescribed parameter is one the model has to guess at."""
    reg, _ = registry()
    for tool in reg.values():
        for name, prop in tool.spec["schema"]["parameters"]["properties"].items():
            assert prop["description"], f"{tool.name}.{name} has no description"


def test_core_tools_registers_exactly_six():
    reg, _ = registry()
    assert sorted(reg) == ["bash", "edit_file", "grep", "list_files", "read_file", "write_file"]


def test_bash_description_names_the_shell():
    """The model should not have to discover the shell one failed command at a time."""
    reg, _ = registry()
    description = reg["bash"].spec["schema"]["description"]
    assert ("cmd.exe" in description) if os.name == "nt" else ("Runs through" in description)


# --- the sandbox -----------------------------------------------------

def test_parent_traversal_is_refused():
    reg, _ = registry()
    for tool, args in [("read_file", {"path": "../../etc/passwd"}),
                       ("write_file", {"path": "../escape.txt", "content": "x"}),
                       ("edit_file", {"path": "../x", "old": "a", "new": "b"})]:
        try:
            reg[tool].run(**args)
            raise AssertionError(f"{tool} allowed a path outside the working directory")
        except PermissionError as e:
            assert "escapes the working directory" in str(e)


def test_absolute_paths_outside_the_workdir_are_refused():
    reg, _ = registry()
    outside = os.path.abspath(os.sep) + "windows" if os.name == "nt" else "/etc/hosts"
    try:
        reg["read_file"].run(path=outside)
        raise AssertionError("an absolute outside path was allowed")
    except PermissionError:
        pass


def test_paths_inside_the_workdir_are_allowed():
    """The guard must not be so tight that ordinary nested work fails."""
    reg, _ = registry()
    assert reg["write_file"].run(path="a/b/c.txt", content="ok") == "Wrote 2 chars to a/b/c.txt"
    assert reg["read_file"].run(path="./a/b/../b/c.txt") == "1\tok"


# --- read_file / write_file / edit_file ------------------------------

def test_write_reports_size_and_creates_parents():
    reg, workdir = registry()
    assert reg["write_file"].run(path="deep/nested/f.txt", content="hello") == \
        "Wrote 5 chars to deep/nested/f.txt"
    assert os.path.isfile(os.path.join(workdir, "deep", "nested", "f.txt"))


def test_read_numbers_lines_from_one():
    reg, _ = registry()
    reg["write_file"].run(path="f.txt", content="alpha\nbeta\n")
    assert reg["read_file"].run(path="f.txt") == "1\talpha\n2\tbeta"


def test_read_truncates_past_the_cap_and_reports_the_total():
    reg, _ = registry()
    total = tools.MAX_READ_LINES + 25
    reg["write_file"].run(path="big.txt", content="".join(f"line{i}\n" for i in range(total)))
    out = reg["read_file"].run(path="big.txt").splitlines()
    assert len(out) == tools.MAX_READ_LINES + 1
    assert out[-1] == f"... truncated: showing {tools.MAX_READ_LINES} of {total} lines"


def test_edit_replaces_a_unique_snippet():
    reg, _ = registry()
    reg["write_file"].run(path="f.txt", content="keep\nchange me\nkeep\n")
    assert reg["edit_file"].run(path="f.txt", old="change me", new="changed") == "Edited f.txt"
    assert reg["read_file"].run(path="f.txt") == "1\tkeep\n2\tchanged\n3\tkeep"


def test_edit_refuses_a_missing_snippet():
    reg, _ = registry()
    reg["write_file"].run(path="f.txt", content="hello\n")
    assert reg["edit_file"].run(path="f.txt", old="nope", new="x") == \
        "ERROR: snippet not found — read the file and copy it exactly"


def test_edit_refuses_an_ambiguous_snippet_and_changes_nothing():
    """An ambiguous edit applied anyway is a silent wrong edit."""
    reg, _ = registry()
    reg["write_file"].run(path="f.txt", content="x\nx\nx\n")
    assert reg["edit_file"].run(path="f.txt", old="x", new="y") == \
        "ERROR: snippet appears 3 times — include more context to make it unique"
    assert reg["read_file"].run(path="f.txt") == "1\tx\n2\tx\n3\tx"


# --- bash ------------------------------------------------------------

def test_bash_returns_output():
    reg, _ = registry()
    assert reg["bash"].run(command="echo hello").strip() == "hello"


def test_bash_runs_in_the_working_directory():
    reg, _ = registry()
    reg["write_file"].run(path="marker.txt", content="found")
    assert "found" in reg["bash"].run(command=print_file_command("marker.txt"))


def test_bash_reports_the_exit_code_when_there_is_no_output():
    """Silence and 'it printed nothing' are different facts."""
    reg, _ = registry()
    assert reg["bash"].run(command="exit 3") == "(exit 3, no output)"


def test_bash_times_out():
    reg, _ = registry()
    assert reg["bash"].run(command=sleep_command(10), timeout="1") == "ERROR: timed out after 1s"


def test_bash_truncates_the_middle_of_huge_output():
    """Head and tail survive, the middle does not.

    Exact tail length is not asserted: the shell may translate the
    trailing newline (cmd's 'type' emits CRLF), which shifts the last
    characters by one or two without changing what the cap is for.
    """
    reg, _ = registry()
    half = tools.MAX_BASH_CHARS // 2
    reg["write_file"].run(path="huge.txt", content="A" * 20000 + "\n" + "Z" * 20000 + "\n")
    out = reg["bash"].run(command=print_file_command("huge.txt"))
    assert "characters truncated" in out
    assert out.startswith("A" * half)            # head kept
    assert out.count("A") == half                # and the rest of it dropped
    assert out.rstrip().endswith("Z" * 1000)     # tail kept
    assert len(out) < 20000                      # from 40k of input


# --- list_files / grep -----------------------------------------------

def test_list_files_default_pattern_includes_top_level_files():
    """'**/*' must not silently mean 'only files in a subdirectory'."""
    reg, _ = registry()
    reg["write_file"].run(path="top.txt", content="x")
    reg["write_file"].run(path="sub/nested.txt", content="x")
    assert sorted(reg["list_files"].run().splitlines()) == ["sub/nested.txt", "top.txt"]


def test_list_files_filters_by_glob():
    reg, _ = registry()
    reg["write_file"].run(path="a.py", content="x")
    reg["write_file"].run(path="b.txt", content="x")
    assert reg["list_files"].run(pattern="*.py") == "a.py"


def test_list_files_skips_ignored_directories():
    reg, _ = registry()
    reg["write_file"].run(path="real.txt", content="x")
    for ignored in tools.IGNORED_DIRS:
        reg["write_file"].run(path=f"{ignored}/hidden.txt", content="x")
    assert reg["list_files"].run() == "real.txt"


def test_list_files_caps_the_entry_count():
    reg, _ = registry()
    extra = 5
    for i in range(tools.MAX_LIST_ENTRIES + extra):
        reg["write_file"].run(path=f"f{i:04d}.txt", content="x")
    out = reg["list_files"].run().splitlines()
    assert len(out) == tools.MAX_LIST_ENTRIES + 1
    assert out[-1] == f"... and {extra} more"


def test_list_files_says_so_when_nothing_matches():
    reg, _ = registry()
    assert reg["list_files"].run(pattern="*.rs") == "(no files matching *.rs)"


def test_grep_reports_path_line_and_text():
    reg, _ = registry()
    reg["write_file"].run(path="f.txt", content="alpha\nbeta\ngamma\n")
    assert reg["grep"].run(regex="^bet") == "f.txt:2: beta"


def test_grep_honours_the_file_glob():
    reg, _ = registry()
    reg["write_file"].run(path="a.py", content="needle\n")
    reg["write_file"].run(path="b.txt", content="needle\n")
    assert reg["grep"].run(regex="needle", pattern="*.py") == "a.py:1: needle"


def test_grep_clips_long_lines():
    reg, _ = registry()
    reg["write_file"].run(path="f.txt", content="needle" + "x" * 5000 + "\n")
    hit = reg["grep"].run(regex="needle")
    assert len(hit.split(": ", 1)[1]) == tools.MAX_GREP_LINE


def test_grep_caps_the_hit_count():
    reg, _ = registry()
    reg["write_file"].run(path="f.txt", content="needle\n" * (tools.MAX_GREP_HITS + 50))
    out = reg["grep"].run(regex="needle").splitlines()
    assert len(out) == tools.MAX_GREP_HITS + 1
    assert out[-1] == f"... stopped at {tools.MAX_GREP_HITS} matches"


def test_grep_says_so_when_nothing_matches():
    reg, _ = registry()
    reg["write_file"].run(path="f.txt", content="alpha\n")
    assert reg["grep"].run(regex="nothing") == "(no matches for nothing)"
