"""Tests for Sthenos.memory -- the base prompt, assembly, and STHENOS.md."""

import os
import tempfile

from Sthenos import memory


def workdir():
    return tempfile.mkdtemp(prefix="sthenos_test_")


# --- the base prompt ---------------------------------------------------

def test_base_prompt_covers_every_required_point():
    """Each contract point must survive as a recognizable instruction."""
    required = ["sthenos", "act, don't narrate", "inspect before assuming",
                "edit_file", "verify after building", "never repeat a failing call",
                "short summary"]
    lowered = memory.BASE_PROMPT.lower()
    for phrase in required:
        assert phrase in lowered, f"{phrase!r} missing from BASE_PROMPT"


# --- build_system_prompt -------------------------------------------------

def test_prompt_names_the_platform_and_the_real_working_directory():
    wd = workdir()
    prompt = memory.build_system_prompt(wd)
    assert os.path.realpath(wd) in prompt
    assert "Platform:" in prompt


def test_prompt_has_no_memory_section_when_sthenos_md_is_absent():
    prompt = memory.build_system_prompt(workdir())
    assert "Project memory" not in prompt


def test_prompt_includes_project_memory_section_once_a_note_exists():
    wd = workdir()
    memory.remember(wd, "the build uses Polars, not pandas")
    prompt = memory.build_system_prompt(wd)
    assert "Project memory (sthenos.md):" in prompt
    assert "the build uses Polars, not pandas" in prompt


def test_prompt_omits_extra_when_empty_and_includes_it_when_given():
    wd = workdir()
    assert "Skills available" not in memory.build_system_prompt(wd, extra="")
    prompt = memory.build_system_prompt(wd, extra="Skills available: none")
    assert "Skills available: none" in prompt


def test_prompt_sections_are_joined_by_blank_lines():
    wd = workdir()
    memory.remember(wd, "a fact")
    prompt = memory.build_system_prompt(wd, extra="extra section")
    assert "\n\n" in prompt
    # four sections: base, platform/workdir, project memory, extra
    assert prompt.count("\n\n") >= 3


# --- remember ------------------------------------------------------------

def test_remember_creates_the_file_and_returns_the_confirmation():
    wd = workdir()
    path = os.path.join(wd, memory.MEMORY_FILE)
    assert not os.path.exists(path)
    result = memory.remember(wd, "first fact")
    assert result == "Remembered in sthenos.md"
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        assert f.read() == "- first fact\n"


def test_remember_appends_as_bullets_across_calls():
    wd = workdir()
    memory.remember(wd, "one")
    memory.remember(wd, "two")
    with open(os.path.join(wd, memory.MEMORY_FILE), encoding="utf-8") as f:
        assert f.read() == "- one\n- two\n"
