# Sthenos

The smallest agent harness that still feels real. Ten files build the
engine -- provider through harness -- plus a CLI and a fleet runner as its
front door. Zero third-party dependencies: the standard library only,
including `urllib` for the API call, so a fresh clone runs with nothing to
`pip install`.

## Running it

Set an API key (`Sthenos_API_KEY` or `ANTHROPIC_API_KEY`), optionally pick a
model with `sthenos_MODEL` (falls back to `provider.DEFAULT_MODEL`), then:

```bash
# headless: one task, one answer, exit 0
python -m Sthenos -p "add a .gitignore for a Python project" -d ./my-project

# interactive: a prompt loop over the working directory
python -m Sthenos -d ./my-project

# resume: continue the most recent session in that directory
python -m Sthenos -d ./my-project --resume
python -m Sthenos -p "keep going" -d ./my-project --resume
```

`--mode` picks the policy (`safe`, `yolo`, `read-only`; default `safe`
interactively, `yolo` headless). Ctrl-D exits the interactive loop; Ctrl-C
interrupts a run without losing it -- the session log is durable the moment
each message lands, so `--resume` always picks up where it stopped.

## Anatomy

| Day | Files | Adds |
|---|---|---|
| 1 | `provider.py`, `loop.py` | the wire format and the turn loop: ask, act, repeat |
| 2 | `tools.py`, `security.py` | six tools derived from function signatures, and the policy gate that decides which calls run |
| 3 | `context.py`, `memory.py`, `skills.py` | compaction so long runs fit the budget, `STHENOS.md` as durable project memory, and skills loaded on demand |
| 4 | `session.py`, `subagent.py`, `harness.py`, `__init__.py` | a session log that survives a crash, `spawn_agent` for delegating self-contained work, and `Harness` wiring it all into one object |
| 5 | `cli.py`, `fleet.py`, `__main__.py` | `python -m sthenos`, and `run_fleet` for running several harnesses at once |

Each module carries its own "why" in a docstring and a short list of design
rules -- read the file before the feature if you want the reasoning, not
just the shape.

## Composing it

`Harness` takes `extra_tools`, so registering a project-specific tool is one
dict entry, not a fork:

```python
import random
from Sthenos import Harness, tool

@tool("Roll an n-sided die", sides="Number of sides (default 6)")
def roll_die(sides="6"):
    return str(random.randint(1, int(sides)))

agent = Harness(".", extra_tools={"roll_die": roll_die})
print(agent.run("Roll a d20 for me"))
```

`spawn_agent` is built the same way internally -- a tool added to the
registry at construction time -- so a sub-agent, a fleet job, and a
hand-written tool are all the same kind of thing to `Harness`: something
with a name, a schema, and a `.run`.
