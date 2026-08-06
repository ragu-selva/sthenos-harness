"""Tests for Sthenos.session -- durable sessions, torn tails, and crash repair."""

import json
import os
import re
import tempfile

from Sthenos import session


def workdir():
    return tempfile.mkdtemp(prefix="sthenos_test_")


def write_lines(path, *lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# --- new_session -------------------------------------------------------

def test_new_session_creates_the_directory():
    wd = workdir()
    session.new_session(wd)
    assert os.path.isdir(session._session_root(wd))


def test_new_session_returns_a_timestamped_slugified_jsonl_path():
    wd = workdir()
    path = session.new_session(wd, label="My Cool Session!!")
    assert re.match(r"^\d+-My-Cool-Session\.jsonl$", os.path.basename(path))


def test_new_session_default_label_is_session():
    wd = workdir()
    path = session.new_session(wd)
    assert os.path.basename(path).endswith("-session.jsonl")


def test_new_session_slug_is_clipped_to_forty_chars():
    wd = workdir()
    path = session.new_session(wd, label="x" * 100)
    slug = os.path.basename(path).split("-", 1)[1][:-len(".jsonl")]
    assert len(slug) == 40


# --- append / load round trip ------------------------------------------

def test_append_and_load_round_trip():
    wd = workdir()
    path = session.new_session(wd)
    session.append(path, {"role": "user", "text": "hi"})
    session.append(path, {"role": "assistant", "text": "hello", "tool_calls": []})
    assert session.load(path) == [
        {"role": "user", "text": "hi"},
        {"role": "assistant", "text": "hello", "tool_calls": []},
    ]


def test_load_of_a_missing_file_returns_an_empty_list():
    wd = workdir()
    assert session.load(os.path.join(wd, "nope.jsonl")) == []


def test_load_stops_at_a_torn_tail_and_keeps_everything_before_it():
    wd = workdir()
    path = os.path.join(wd, "torn.jsonl")
    write_lines(path, json.dumps({"role": "user", "text": "ok"}),
                '{"role": "assistant", "text": "cut off mid-wri')
    assert session.load(path) == [{"role": "user", "text": "ok"}]


# --- repair --------------------------------------------------------------

def test_load_backfills_the_tool_result_a_crash_interrupted():
    wd = workdir()
    path = os.path.join(wd, "s.jsonl")
    assistant_msg = {"role": "assistant", "text": "", "tool_calls": [
        {"name": "write_file", "args": {}}, {"name": "read_file", "args": {}}]}
    write_lines(path,
                json.dumps({"role": "user", "text": "go"}),
                json.dumps(assistant_msg),
                json.dumps({"role": "tool", "name": "write_file", "text": "Wrote 1 chars"}))
    result = session.load(path)
    assert len(result) == 4
    assert result[-1] == {"role": "tool", "name": "read_file",
                           "text": "Interrupted before this ran (process restarted)."}


def test_load_repairs_every_tool_call_when_none_were_answered():
    wd = workdir()
    path = os.path.join(wd, "s.jsonl")
    assistant_msg = {"role": "assistant", "text": "", "tool_calls": [
        {"name": "bash", "args": {}}, {"name": "grep", "args": {}}]}
    write_lines(path, json.dumps({"role": "user", "text": "go"}), json.dumps(assistant_msg))
    result = session.load(path)
    assert [m["role"] for m in result[1:]] == ["assistant", "tool", "tool"]
    assert [m["name"] for m in result[2:]] == ["bash", "grep"]


def test_load_does_not_repair_when_every_tool_call_is_already_answered():
    wd = workdir()
    path = os.path.join(wd, "s.jsonl")
    assistant_msg = {"role": "assistant", "text": "", "tool_calls": [{"name": "write_file", "args": {}}]}
    write_lines(path,
                json.dumps({"role": "user", "text": "go"}),
                json.dumps(assistant_msg),
                json.dumps({"role": "tool", "name": "write_file", "text": "Wrote 1 chars"}))
    assert len(session.load(path)) == 3


def test_load_does_not_repair_an_assistant_message_with_no_tool_calls():
    wd = workdir()
    path = os.path.join(wd, "s.jsonl")
    write_lines(path,
                json.dumps({"role": "user", "text": "go"}),
                json.dumps({"role": "assistant", "text": "done", "tool_calls": []}))
    assert len(session.load(path)) == 2


def test_load_with_no_assistant_message_at_all_is_a_no_op():
    wd = workdir()
    path = os.path.join(wd, "s.jsonl")
    write_lines(path, json.dumps({"role": "user", "text": "go"}))
    assert session.load(path) == [{"role": "user", "text": "go"}]


# --- latest --------------------------------------------------------------

def test_latest_is_none_with_no_sessions_directory():
    assert session.latest(workdir()) is None


def test_latest_is_none_with_an_empty_sessions_directory():
    wd = workdir()
    os.makedirs(session._session_root(wd))
    assert session.latest(wd) is None


def test_latest_returns_the_newest_by_filename():
    wd = workdir()
    root = session._session_root(wd)
    os.makedirs(root)
    open(os.path.join(root, "100-a.jsonl"), "w").close()
    open(os.path.join(root, "200-b.jsonl"), "w").close()
    assert session.latest(wd) == os.path.join(root, "200-b.jsonl")


def test_latest_ignores_non_jsonl_files():
    wd = workdir()
    root = session._session_root(wd)
    os.makedirs(root)
    open(os.path.join(root, "999-notes.txt"), "w").close()
    open(os.path.join(root, "100-a.jsonl"), "w").close()
    assert session.latest(wd) == os.path.join(root, "100-a.jsonl")
