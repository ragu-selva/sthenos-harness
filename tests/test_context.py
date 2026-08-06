"""Tests for Sthenos.context -- when compaction fires and what it produces.

provider.complete makes a real network call, so every test here swaps it
for a fake that records what it was sent and returns a fixed summary.
fake_complete is a plain context manager, not a fixture -- see
tests/__init__.py on why this file stays dependency-free.
"""

from contextlib import contextmanager

from Sthenos import context, provider


@contextmanager
def fake_complete(summary="SUMMARY", calls=None):
    """Swap provider.complete for one that records calls and never hits the network."""
    original = provider.complete

    def fake(model, system, messages, tools=None):
        if calls is not None:
            calls.append({"model": model, "system": system, "messages": messages})
        return {"text": summary, "tool_calls": [], "usage": {"input": 0, "output": 0}}

    provider.complete = fake
    try:
        yield
    finally:
        provider.complete = original


def user(text):
    return {"role": "user", "text": text}


def assistant(text, tool_calls=None):
    return {"role": "assistant", "text": text, "tool_calls": tool_calls or []}


def tool_msg(name, text):
    return {"role": "tool", "name": name, "text": text}


# --- estimate_tokens ---------------------------------------------------

def test_estimate_tokens_is_total_chars_over_chars_per_token():
    messages = [user("a" * 40), assistant("b" * 20)]
    total_chars = sum(len(str(m)) for m in messages)
    assert context.estimate_tokens(messages) == total_chars // context.CHARS_PER_TOKEN


# --- when compaction does not fire -------------------------------------

def test_within_budget_returns_the_same_list_and_skips_the_provider():
    messages = [user("short")] * 10
    calls = []
    with fake_complete(calls=calls):
        result = context.compact("model-x", messages, budget_tokens=10_000)
    assert result is messages
    assert calls == []


def test_short_history_returns_unchanged_even_over_budget():
    """At most KEEP_RECENT + 1 messages is too little to bother summarizing."""
    messages = [user("x" * 1000) for _ in range(context.KEEP_RECENT + 1)]
    calls = []
    with fake_complete(calls=calls):
        result = context.compact("model-x", messages, budget_tokens=1)
    assert result is messages
    assert calls == []


# --- when compaction fires ----------------------------------------------

def test_compact_replaces_old_messages_with_one_summary_and_keeps_the_recent_tail():
    old = [user(f"turn {i}") for i in range(10)]
    recent = [assistant(f"recent {i}") for i in range(context.KEEP_RECENT)]
    with fake_complete(summary="THE SUMMARY"):
        result = context.compact("model-x", old + recent, budget_tokens=1)
    assert result[0] == {"role": "user", "text": "[Conversation so far, compacted]\nTHE SUMMARY"}
    assert result[1:] == recent


def test_compact_calls_the_provider_once_with_the_compression_system_prompt():
    messages = [user(f"turn {i}") for i in range(20)]
    calls = []
    with fake_complete(calls=calls):
        context.compact("model-x", messages, budget_tokens=1)
    assert len(calls) == 1
    assert calls[0]["model"] == "model-x"
    assert calls[0]["system"] == context.COMPACT_SYSTEM


def test_kept_slice_drops_a_leading_orphaned_tool_result():
    old = [user(f"turn {i}") for i in range(5)]
    recent = [tool_msg("read_file", "orphan"), assistant("ok"),
              user("r0"), user("r1"), user("r2"), user("r3")]
    assert len(recent) == context.KEEP_RECENT
    with fake_complete():
        result = context.compact("model-x", old + recent, budget_tokens=1)
    assert result[1]["role"] != "tool"
    assert result[1] == recent[1]


def test_compaction_needs_more_than_the_budget_check_alone():
    """Over budget but at the message-count floor still returns unchanged."""
    messages = [user("x" * 10_000) for _ in range(context.KEEP_RECENT + 1)]
    calls = []
    with fake_complete(calls=calls):
        result = context.compact("model-x", messages, budget_tokens=1)
    assert result is messages
    assert calls == []


# --- transcript rendering ------------------------------------------------

def test_render_transcript_names_tool_calls_and_tool_results():
    messages = [
        assistant("writing the file", tool_calls=[{"name": "write_file", "args": {}}]),
        tool_msg("write_file", "Wrote 5 chars to f.txt"),
    ]
    text = context._render_transcript(messages)
    assert "[called: write_file]" in text
    assert "tool (write_file): Wrote 5 chars to f.txt" in text


def test_render_transcript_clips_long_text():
    long_text = "x" * (context.TRANSCRIPT_CLIP_CHARS + 50)
    text = context._render_transcript([user(long_text)])
    assert len(text.splitlines()) == 1
    assert "+50 chars" in text
