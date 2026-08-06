"""Tests for Sthenos.skills -- the catalog, its prompt, and reading one skill."""

import os
import tempfile

from Sthenos import skills


def workdir():
    return tempfile.mkdtemp(prefix="sthenos_test_")


def write_skill(wd, name, body, description="does a thing"):
    skill_dir = os.path.join(wd, skills.SKILLS_DIR, name)
    os.makedirs(skill_dir, exist_ok=True)
    front_matter = f"---\ndescription: {description}\n---\n"
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(front_matter + body)


# --- catalog ---------------------------------------------------------

def test_catalog_is_empty_with_no_skills_directory():
    assert skills.catalog(workdir()) == {}


def test_catalog_skips_a_directory_with_no_skill_md():
    wd = workdir()
    os.makedirs(os.path.join(wd, skills.SKILLS_DIR, "empty-dir"))
    assert skills.catalog(wd) == {}


def test_catalog_reads_name_description_and_path():
    wd = workdir()
    write_skill(wd, "brand-voice", "Speak like a pirate.", description="pirate voice for copy")
    found = skills.catalog(wd)
    assert set(found) == {"brand-voice"}
    assert found["brand-voice"]["description"] == "pirate voice for copy"
    assert found["brand-voice"]["path"] == os.path.join(wd, "skills", "brand-voice", "SKILL.md")


def test_catalog_handles_a_skill_with_no_front_matter():
    wd = workdir()
    skill_dir = os.path.join(wd, skills.SKILLS_DIR, "plain")
    os.makedirs(skill_dir)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("Just instructions, no front matter.")
    assert skills.catalog(wd)["plain"]["description"] == ""


def test_catalog_covers_multiple_skills():
    wd = workdir()
    write_skill(wd, "a", "do a", description="does a")
    write_skill(wd, "b", "do b", description="does b")
    assert set(skills.catalog(wd)) == {"a", "b"}


# --- catalog_prompt ----------------------------------------------------

def test_catalog_prompt_is_empty_string_with_no_skills():
    assert skills.catalog_prompt(workdir()) == ""


def test_catalog_prompt_lists_each_skill_by_name_and_description():
    wd = workdir()
    write_skill(wd, "brand-voice", "Speak like a pirate.", description="pirate voice for copy")
    prompt = skills.catalog_prompt(wd)
    assert prompt.startswith("Skills available (load one with the use_skill tool when relevant):")
    assert "- brand-voice: pirate voice for copy" in prompt


# --- read_skill ----------------------------------------------------------

def test_read_skill_returns_the_full_file():
    wd = workdir()
    write_skill(wd, "brand-voice", "Speak like a pirate, arr.", description="pirate voice")
    text = skills.read_skill(wd, "brand-voice")
    assert "Speak like a pirate, arr." in text
    assert text.startswith("---")


def test_read_skill_reports_a_miss_and_names_whats_available():
    wd = workdir()
    write_skill(wd, "brand-voice", "x")
    result = skills.read_skill(wd, "nope")
    assert result == "ERROR: no skill named nope. Available: brand-voice"


def test_read_skill_names_availability_as_none_when_the_catalog_is_empty():
    assert skills.read_skill(workdir(), "anything") == "ERROR: no skill named anything. Available: (none)"
