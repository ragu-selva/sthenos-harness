"""Day 2 -- the policy that decides whether a tool call runs.

run_loop calls before_tool with a tool call and does what it is told:
None runs the tool, a string becomes "BLOCKED: <reason>" that the model
reads as the result. Policy.check is that callback. It is the whole
security layer today, and it lives here rather than in the loop so that
the loop never grows a notion of what "dangerous" means -- swap this
file and the agent's judgment changes without a line of loop.py moving.

Design rules:
  - order is the design. Deny patterns are checked before mode, so no
    mode can turn them off; yolo is permissive about everything else and
    still cannot rm -rf ~. A policy where the escape hatch outranks the
    prohibition is not a policy.
  - a blocked call is not an error. It returns a sentence explaining the
    refusal, the model reads it as a tool result, and the conversation
    continues -- the agent gets to explain or choose another route
    instead of the session dying on a raised exception.
  - refusal is the default. approver=None means "no" rather than "yes":
    a policy in safe mode with nobody wired up to ask must not silently
    behave like yolo.
  - DENY_PATTERNS is a speed bump, not a boundary. A blocklist over
    shell strings loses to anyone trying -- base64, a variable, a
    different spelling. The real containment is tools.resolve() and the
    approver; these patterns stop an agent that is confidently wrong,
    which is the failure that actually happens.
"""

import re

# Reading cannot destroy anything, so it never needs a decision.
READ_TOOLS = {"read_file", "list_files", "grep"}

MODES = ("read-only", "safe", "yolo")

DENY_PATTERNS = [
    # rm with both -r and -f in any order, aimed at the filesystem root
    # or the home directory. 'rm -rf build/' is ordinary work and passes.
    r"\brm\b(?=[^;&|]*\s-[\w-]*r)(?=[^;&|]*\s-[\w-]*f)"
    r"[^;&|]*\s(?:/|~|\$\{?HOME\}?)(?:/\S*)?(?=\s|;|&|\||$)",
    r"\bsudo\b",
    r"\bmkfs(?:\.\w+)?\b",
    r"\bdd\s+if=",
    r"\bcurl\b[^;&|]*\|\s*(?:sudo\s+)?(?:ba|z|k)?sh\b",
    r"\bgit\s+push\b[^;&|]*(?:--force\b|\s-f\b)",
    r">>?\s*/dev/sd[a-z]",
]


class Policy:
    """Decides whether a tool call may run, per mode and the deny list."""

    def __init__(self, mode="safe", approver=None):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        self.mode = mode
        # No approver means no approvals -- see the module docstring.
        self.approver = approver or (lambda call, reason: False)

    def check(self, call):
        """Return None to allow the call, or a reason string to block it."""
        name = call["name"]
        args = call.get("args", {})

        if name == "bash":
            command = args.get("command", "")
            for pattern in DENY_PATTERNS:
                if re.search(pattern, command, re.IGNORECASE):
                    return (f"{command!r} matches a denied command pattern "
                            f"({pattern!r}); this is refused in every mode")

        if name in READ_TOOLS or self.mode == "yolo":
            return None

        if self.mode == "read-only":
            return f"{name} can modify the system and the policy is read-only"

        reason = f"{name} can modify the system"
        if self.approver(call, reason):
            return None
        return f"{name} was not approved"
