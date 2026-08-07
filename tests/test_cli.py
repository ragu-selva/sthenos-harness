"""Tests for Sthenos.cli -- argument parsing and the event/approval helpers, no network."""

import builtins
import io
import tempfile
from contextlib import contextmanager, redirect_stdout

from Sthenos import cli, provider, session


def workdir():
    return tempfile.mkdtemp(prefix="sthenos_test_")


@contextmanager
def fake_complete(text="done", tool_calls=None):
    original = provider.complete

    def fake(model, system, messages, tools=None):
        return {"text": text, "tool_calls": tool_calls or [], "usage": {"input": 0, "output": 0}}

    provider.complete = fake
    try:
        yield
    finally:
        provider.complete = original


@contextmanager
def fake_input(answer):
    original = builtins.input
    builtins.input = lambda prompt="": answer
    try:
        yield
    finally:
        builtins.input = original


# --- argument parsing --------------------------------------------------------

def test_defaults():
    args = cli.build_parser().parse_args([])
    assert args.prompt is None
    assert args.workdir == "."
    assert args.model is None
    assert args.mode is None
    assert args.resume is False
    assert args.max_turns == 120


def test_headless_flags_parse():
    args = cli.build_parser().parse_args(["-p", "do it", "-d", "somewhere", "-m", "model-x",
                                           "--mode", "yolo", "--resume", "--max-turns", "5"])
    assert args.prompt == "do it"
    assert args.workdir == "somewhere"
    assert args.model == "model-x"
    assert args.mode == "yolo"
    assert args.resume is True
    assert args.max_turns == 5


def test_mode_rejects_an_unknown_value():
    try:
        cli.build_parser().parse_args(["--mode", "nonsense"])
    except SystemExit:
        pass
    else:
        raise AssertionError("expected argparse to reject an invalid --mode")


# --- the event printer --------------------------------------------------------

def test_clip_leaves_short_text_alone():
    assert cli._clip("hi", 10) == "hi"


def test_clip_truncates_long_text_and_notes_how_much():
    clipped = cli._clip("x" * 20, 5)
    assert clipped.startswith("xxxxx...")
    assert "+15" in clipped


def test_print_event_prints_assistant_text_and_a_tool_call_line():
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli.print_event("assistant", {"text": "hello",
                                       "tool_calls": [{"name": "read_file", "args": {"path": "x"}}]})
    out = buf.getvalue()
    assert "hello" in out
    assert "-> read_file(" in out


def test_print_event_tool_end_shows_only_the_first_line_of_the_result():
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli.print_event("tool_end", {"name": "read_file", "result": "line one\nline two"})
    out = buf.getvalue()
    assert "line one" in out
    assert "line two" not in out


# --- the approver --------------------------------------------------------

def test_make_approver_shows_the_call_and_approves_on_y():
    approve = cli.make_approver()
    with fake_input("y"):
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = approve({"name": "bash", "args": {"command": "rm x"}}, "bash can modify the system")
    assert result is True
    assert "bash can modify the system" in buf.getvalue()


def test_make_approver_denies_on_anything_but_y():
    approve = cli.make_approver()
    with fake_input("n"):
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = approve({"name": "bash", "args": {}}, "reason")
    assert result is False


# --- main() headless ----------------------------------------------------------

def test_main_headless_runs_the_prompt_and_persists_a_session():
    wd = workdir()
    with fake_complete(text="done headless"):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["-p", "do the thing", "-d", wd])
    assert code == 0
    path = session.latest(wd)
    assert path is not None
    assert session.load(path)[-1] == {"role": "assistant", "text": "done headless", "tool_calls": []}


def test_main_headless_resume_continues_the_same_session():
    wd = workdir()
    with fake_complete(text="first"):
        with redirect_stdout(io.StringIO()):
            cli.main(["-p", "first task", "-d", wd])
    first_path = session.latest(wd)

    with fake_complete(text="second"):
        with redirect_stdout(io.StringIO()):
            cli.main(["-p", "second task", "-d", wd, "--resume"])

    assert session.latest(wd) == first_path
    messages = session.load(first_path)
    assert messages[0] == {"role": "user", "text": "first task"}
    assert messages[-1] == {"role": "assistant", "text": "second", "tool_calls": []}
