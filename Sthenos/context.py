"""Day 3 -- keeping the message list from outgrowing the model's context.

A long-running agent appends to messages every turn and nothing ever
removes anything; left alone that list eventually stops fitting in a
call at all. compact() is the fix, and it lives in its own module for
the same reason security.py does: loop.py's before_turn socket exists
so this can plug in without the loop knowing what "too long" means or
how a summary gets made.

Design rules:
  - the loop never sees a token count. It calls before_turn(messages)
    and gets a message list back; whether that list changed, and why,
    is entirely this module's business.
  - compaction is a summary, not a deletion. The old turns become one
    user message the model reads like anything else it wrote earlier --
    dense prose that names the task, the files, the decisions, and
    what is still open, not a truncated transcript.
  - the kept tail is real messages, verbatim. Only the old half is
    ever summarized; the last few turns stay exact so the model isn't
    reasoning from a lossy account of what it just did.
  - a tool message can never lead the kept slice. The wire format
    pairs a tool result to the call before it (see provider._to_wire);
    a tool result with no call in front of it is a message the
    provider cannot place.
"""

import logging

from . import provider

CHARS_PER_TOKEN = 4
KEEP_RECENT = 6

# How much of each old message's text survives into the transcript the
# summarizer reads. Generous enough that a file path or an error message
# isn't cut off mid-word, small enough that summarizing the summary input
# doesn't itself become the thing blowing the budget.
TRANSCRIPT_CLIP_CHARS = 300

COMPACT_SYSTEM = ("You compress agent transcripts. Preserve: the original task, every "
                   "file created or edited and its purpose, key decisions, unresolved "
                   "errors, and what remains to be done. Be dense and factual.")

logger = logging.getLogger(__name__)


def estimate_tokens(messages):
    """Rough token count for the whole message list: total chars / CHARS_PER_TOKEN.

    Not a real tokenizer -- str() over the neutral message dicts is cheap
    and provider-agnostic. It only has to be a consistent enough proxy to
    decide when a budget is exceeded, not an exact count.
    """
    return sum(len(str(m)) for m in messages) // CHARS_PER_TOKEN


def compact(model, messages, budget_tokens):
    """Summarize everything but the last KEEP_RECENT messages if over budget.

    Below budget_tokens, or with too few messages for a summary to make
    sense, messages comes back unchanged. Otherwise the old messages are
    rendered into a plain transcript, summarized in one provider call, and
    replaced by a single "compacted" user message in front of the exact
    recent tail.
    """
    if estimate_tokens(messages) <= budget_tokens or len(messages) <= KEEP_RECENT + 1:
        return messages

    old, recent = messages[:-KEEP_RECENT], messages[-KEEP_RECENT:]
    while recent and recent[0]["role"] == "tool":
        # An orphaned tool result: the call it answers was summarized
        # away, so the provider has nothing to pair it with.
        recent = recent[1:]

    transcript = _render_transcript(old)
    reply = provider.complete(model, COMPACT_SYSTEM, [{"role": "user", "text": transcript}])
    summary = reply["text"]
    logger.info("compacted %d messages (~%d tokens) into a %d-char summary; kept %d recent",
                len(old), estimate_tokens(old), len(summary), len(recent))

    return [{"role": "user", "text": f"[Conversation so far, compacted]\n{summary}"}] + recent


def _clip(text, limit):
    """Cut text to limit chars, noting how much was dropped."""
    text = str(text)
    return text if len(text) <= limit else text[:limit] + f"... (+{len(text) - limit} chars)"


def _render_transcript(messages):
    """Render old messages as plain lines: role, tool name, clipped text, tool calls named.

    Not the wire format and not JSON -- this is read by the model doing
    the summarizing, once, so it should read like a transcript rather
    than a data structure.
    """
    lines = []
    for msg in messages:
        role = msg["role"]
        text = _clip(msg.get("text") or "", TRANSCRIPT_CLIP_CHARS)
        if role == "tool":
            lines.append(f"tool ({msg['name']}): {text}")
        elif role == "assistant":
            calls = msg.get("tool_calls") or []
            called = f" [called: {', '.join(c['name'] for c in calls)}]" if calls else ""
            lines.append(f"assistant: {text}{called}")
        else:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)
