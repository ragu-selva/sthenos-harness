"""Day 1 -- the provider boundary.

Sthenos talks to exactly one place outside the process: this file. Every
other module hands it the neutral message list -- {"role": "user"/
"assistant"/"tool", "text", ...} -- and gets {"text", "tool_calls",
"usage"} back; nothing above this file knows which vendor or wire format
sits behind api_key(). Swap providers by rewriting complete()/_to_wire()/
_from_wire() alone. Today's provider is Anthropic's Messages API -- the
key available here, not an architectural assumption.

Design rules: the neutral format is fixed, only _to_wire/_from_wire speak
dialect; retries are this file's problem, not the loop's, so callers see
a clean result or a RuntimeError worth showing a human; and the thought-
signature echo -- models with cross-turn reasoning state attach a
signature that must be replayed verbatim next call, or the model loses
its place. Claude's plain tool_use carries none (that needs extended
thinking, temperature 1, out of scope today) -- the echo path stays
wired up so enabling it later is a one-line change, not a redesign.
"""

import json
import os
import time
import urllib.error
import urllib.request

API_ROOT = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5"
_ANTHROPIC_VERSION = "2023-06-01"

def api_key():
    """Read the API key from Sthenos_API_KEY, falling back to ANTHROPIC_API_KEY."""
    key = os.environ.get("Sthenos_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Set Sthenos_API_KEY or ANTHROPIC_API_KEY in your environment.")
    return key

def complete(model, system, messages, tools=None):
    """Send one turn to the model; return {"text", "tool_calls", "usage"}.

    tools is a list of {"schema": {"name", "description", "parameters"}}
    specs, one per callable tool, or empty/None for a plain text turn.
    """
    tools = tools or []
    body = {
        "model": model, "system": system, "messages": _to_wire(messages),
        "max_tokens": 8192, "temperature": 0.4,
    }
    if tools:
        body["tools"] = [_to_tool(t["schema"]) for t in tools]
    return _from_wire(_post(API_ROOT, body))

def _to_tool(schema):
    """Map a neutral {name, description, parameters} spec to Claude's input_schema shape."""
    return {"name": schema["name"], "description": schema["description"],
            "input_schema": schema["parameters"]}

def _to_wire(messages):
    """Translate the neutral message list into Claude's content-block format.

    Walks the whole list at once: a tool_result block needs the
    tool_use_id of the call it answers, which the neutral tool message
    doesn't carry -- call order (one turn's results, in order, before
    the next turn) is what pairs them back up.
    """
    wire, pending_ids = [], []
    for msg in messages:
        role = msg["role"]
        if role == "user":
            wire.append({"role": "user", "content": [{"type": "text", "text": msg["text"]}]})
        elif role == "assistant":
            blocks = [{"type": "text", "text": msg["text"]}] if msg["text"] else []
            pending_ids = []
            for i, call in enumerate(msg["tool_calls"]):
                call_id = f"call_{len(wire)}_{i}"
                pending_ids.append(call_id)
                block = {"type": "tool_use", "id": call_id, "name": call["name"], "input": call["args"]}
                if call.get("signature"):  # echo verbatim -- see module docstring
                    block["signature"] = call["signature"]
                blocks.append(block)
            wire.append({"role": "assistant", "content": blocks})
        else:  # role == "tool"
            call_id = pending_ids.pop(0) if pending_ids else msg["name"]
            wire.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": call_id, "content": msg["text"]}]})
    return wire

def _from_wire(data):
    """Parse a Messages API response into the neutral {"text", "tool_calls", "usage"} shape."""
    text_parts, tool_calls = [], []
    for block in data.get("content", []):
        if block["type"] == "text":
            text_parts.append(block["text"])
        elif block["type"] == "tool_use":  # "thinking" blocks, if any, are skipped here
            tool_calls.append({"name": block["name"], "args": block.get("input", {}),
                                "signature": block.get("signature")})
    usage = data.get("usage", {})
    return {"text": "".join(text_parts), "tool_calls": tool_calls,
            "usage": {"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)}}

def _post(url, body, retries=5):
    """POST JSON to the provider with auth headers, retrying transient failures.

    429/500/502/503 and network errors retry with backoff (2**attempt*2
    seconds); any other HTTP error fails fast with status + truncated body.
    """
    headers = {"Content-Type": "application/json", "x-api-key": api_key(),
               "anthropic-version": _ANTHROPIC_VERSION}
    data = json.dumps(body).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError(f"HTTP {e.code}: {e.read()[:400].decode('utf-8', 'replace')}")
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise
