# Sthenos Harness: architecture and implementation review

This review examines runtime commit [`b8b6309`](https://github.com/ragu-selva/sthenos-harness/commit/b8b6309). Findings distinguish code behavior, locally reproduced results, and recommendations. Only documentation was changed as part of this review.

## Project summary

**Sthenos is an independently implemented, standard-library Python harness that gives a language model the tools and execution state needed to perform local coding tasks.** It owns the model/tool loop, policy checks, context management, Markdown project memory, skill loading, JSONL conversations, child-agent construction, and concurrent job execution.

Its central abstraction is `Harness(workdir, ...)`. A caller constructs an agent, optionally resumes a conversation, and submits tasks with `run(task)`. The model chooses registered tools; the runtime checks policy, executes calls, records results, and asks the model what to do next.

Anthropic supplies the model intelligence. Sthenos supplies the surrounding runtime directly, without invoking an existing coding-agent product or importing a third-party agent framework. Reviewing the code establishes that implementation structure; it cannot establish the historical authorship process or comparative performance against other products.

Its strongest present positioning is a compact, understandable, extensible coding-agent runtime for local workflows. The repository does not contain comparative benchmarks establishing universal replacement of mature coding agents, production service controls, or domain-specific financial engines.

## Architecture and execution model

| Layer | What it owns | Design consequence |
| --- | --- | --- |
| [Provider](../Sthenos/provider.py) | Anthropic translation, credentials, HTTP transport, retries, and usage extraction. | Vendor-specific transport is concentrated in one module; only one adapter exists. |
| [Loop](../Sthenos/loop.py) | Model turns, sequential tool calls, error-to-text conversion, and stopping. | Policy and compaction enter through callbacks instead of being embedded in tool execution. |
| [Tools](../Sthenos/tools.py) | Function-derived schemas and six local coding tools. | Extensions use small Python functions; validation and side-effect handling remain the author's responsibility. |
| [Policy](../Sthenos/security.py) | A tool-name read allowlist, shell deny patterns, and approvals. | Decisions are separable from the loop; enforcement remains process-local and heuristic. |
| [Context](../Sthenos/context.py) | Size estimation and model-generated history summaries. | Long conversations can shrink, at the cost of lossy context. |
| [Memory](../Sthenos/memory.py) and [skills](../Sthenos/skills.py) | Markdown knowledge and instructions. | State is inspectable without database or retrieval infrastructure. |
| [Sessions](../Sthenos/session.py) | JSONL recording, discovery, loading, and incomplete-call repair. | Conversations can resume across processes, subject to durability limits. |
| [Harness](../Sthenos/harness.py) | Construction, reusable messages, persistence hooks, and child configuration. | One object supports multiple tasks; prompt/tool configuration is largely a construction-time snapshot. |
| [Sub-agents](../Sthenos/subagent.py) and [fleet](../Sthenos/fleet.py) | Synchronous delegation and concurrent independent jobs. | Delegation reduces parent context; fleet execution overlaps jobs without coordinating changes. |
| [CLI](../Sthenos/cli.py) | Arguments, interactive input, approval prompts, and event printing. | Interactive and headless callers use the same harness. |

### The control loop

The loop sends the system prompt, conversation, and tool schemas to the provider. An assistant response enters history before tool execution. Each tool call passes through policy; refusals become `BLOCKED` results, unknown tools become `ERROR` results, and ordinary exceptions from a tool's `run` function become readable error text. The model can revise its next action after a failed call.

A response without tool calls finishes the run. Otherwise, results enter the conversation and the next turn begins. The harness defaults to 120 turns, followed by one additional wrap-up response without tools. This is a bounded conversational loop, not a scheduler that independently checks acceptance criteria.

Not all exceptions are converted to tool results: policy callbacks, event callbacks, compaction, and provider failures can still escape. Persistence is attempted in `finally`, but a returned answer does not independently establish task success.

### Provider behavior

The adapter posts JSON to Anthropic's Messages API through `urllib`. It requests up to 8,192 output tokens, uses a 600-second HTTP timeout, and makes up to five attempts for selected transient errors: HTTP 429/500/502/503 and network/timeout failures. Backoff delays are 2, 4, 8, and 16 seconds for repeated retryable failures.

The neutral message representation decouples most runtime code from provider content blocks. Replacing the vendor still requires implementation work. There is no adapter registry, base-URL CLI option, streaming path, or implemented OpenAI/local-model backend.

The literal default model is `claude-sonnet-5`; no live availability check was performed. Credentials come from `Sthenos_API_KEY` or `ANTHROPIC_API_KEY`. An explicit model overrides `sthenos_MODEL`, which overrides the fallback.

Input/output token counts appear in assistant event payloads but are not aggregated into a cost ledger. The response parser does not preserve stop reasons, so the loop cannot explicitly distinguish ordinary completion from an output-limit stop. A signature echo path exists, but extended-thinking support is not fully implemented or validated.

### Memory, skills, and compaction

| State | Purpose | Important limit |
| --- | --- | --- |
| `STHENOS.md` | Carry project facts into newly constructed agents. | Entire file enters the system prompt; no selective retrieval, size limit, provenance, or automatic conflict resolution. |
| `skills/<name>/SKILL.md` | Load specialized instructions when needed. | Instructions guide the model; there is no enforced workflow graph or skill execution engine. |
| Conversation messages | Hold tasks, actions, results, and follow-up requests. | Older context can be summarized and lose detail. |

Although earlier module prose refers to rebuilding memory “per run,” the current `Harness` constructs its system prompt once. Notes appended with `remember` become available to a new harness automatically; the existing instance does not reread the file into its system prompt. Newly added skill directories are likewise not automatically advertised to an existing agent.

Compaction estimates tokens as message-dictionary string length divided by four, excluding the system prompt and tool schemas. At more than seven messages and above the configured threshold, it summarizes the older prefix and retains up to six recent messages. Leading tool results without their assistant calls are removed from the retained tail.

The summarizer sees only the first 300 characters of each old message's text. Assistant tool calls are represented by names rather than full arguments. File edits, errors, and constraints beyond those limits may disappear from active context even though original recorded messages remain on disk. Removed orphaned results are not moved into the summarized prefix. The retained tail is not rechecked against a hard size limit, and an oversized short conversation can skip compaction entirely.

The default `600_000` threshold is therefore an approximate trigger, not a promise that every selected model accepts the request. Model-aware budgeting and retrieval of earlier evidence would improve long-running behavior.

### Delegation and concurrency

`spawn_agent` invokes `child.run(task)` synchronously. Children have fresh message lists, the same working directory and policy object, inherited model and per-run limits, and `persist=False`. A child may create a grandchild, but a depth-two agent cannot delegate further. Only the final child report enters the parent's model-visible transcript; events are forwarded to the shared callback.

This isolates conversation context, not files or permissions. Children can change the same project and memory. Parent `extra_tools` are omitted from `_make_child`, so custom capabilities available to the parent may be unavailable to a delegated task. A child rebuilds its prompt from current files rather than inheriting the parent's conversation.

`run_fleet` uses a thread pool with four workers by default. It constructs one harness per job, preserves result order, and converts ordinary job exceptions into results. It does not handle dependencies, partition a shared project, acquire locks, merge edits, limit aggregate usage, or create durable scheduling state. A depth cap limits nested delegation but does not limit total children requested across turns.

## Security and execution boundaries

The policy is useful for interactive approvals and accidental-operation checks. It is not secure isolation for untrusted code or repositories.

| Finding | Evidence | Effect |
| --- | --- | --- |
| Shell execution retains host permissions. | `bash` uses `subprocess.run(..., shell=True, cwd=root)`. | A working directory does not restrict file or network access. |
| Search follows file symlinks outside the project. | `grep` opens walked paths without `resolve()`; reproduced with a temporary symlink. | An allowed read tool can expose outside content even though `read_file` blocks that symlink. |
| Policy depends on tool names. | `READ_TOOLS` is fixed; `extra_tools` can replace existing names. | A custom replacement inherits a read name's permission treatment regardless of behavior. |
| Deny patterns recognize selected spellings. | Regex matching applies only to calls named `bash`. | Equivalent operations and custom code are outside comprehensive enforcement. |
| Read-only covers model tool permissions. | The harness still creates directories and session files. | It does not promise zero filesystem writes by the runtime. |
| Full skill reads require permission. | `use_skill` is absent from `READ_TOOLS`. | Read-only cannot load skills; safe mode requires approval for them. |
| State is ordinary local text. | No built-in encryption/redaction; debug logs print request/response bodies. | Project content can be recorded locally and sent to the provider when included in context. |

Direct read/write/edit tools normalize paths with `realpath` and check the project prefix, helping with ordinary traversal and symlink escapes. That protection is not applied uniformly to search, memory, or skill access and does not defend against concurrent filesystem races. Custom tools run unrestricted Python unless their authors implement narrower behavior.

For untrusted projects, a separate process/container boundary with restricted mounts, credentials, and network access is the appropriate next engineering layer. Tool metadata should distinguish reads, writes, command execution, and approval requirements rather than infer behavior from names.

## Session recovery and durability

The JSONL design is useful: it is inspectable, easy to parse, and records the original conversation before normal compaction. Existing tests cover ordinary round trips, discovery, resuming valid logs, stopping at a torn tail, and filling missing final tool results.

Repeated continuation of damaged logs needs stronger guarantees:

1. **Torn-line continuation is not repaired on disk — reproduced.** A log with one valid line and a partial JSON line loads its valid prefix. A resumed run appends to the same file without removing or separating the damaged tail. On later reload, parsing stops there again and the continuation is not recovered. A temporary-file probe reproduced this with a fake model response.
2. **Interruption placeholders describe an unknown outcome too confidently — code review.** Missing results are filled with “Interrupted before this ran.” A command may already have modified a file before its result was recorded. Recovery should label the outcome unknown and inspect state before repeating actions.
3. **Synthetic repairs are not durable repair events — code review.** `resume()` sets the recorded-message index to the repaired in-memory list length. Inserted placeholders are therefore not separately written back before later messages. The disk log does not preserve the repair history the resumed process saw.
4. **Session names can collide — reproduced.** Filenames use whole-second timestamps plus task-derived labels. Identical labels created within the same second return the same path, including for agents sharing a directory.
5. **Writes are not transactional — code review.** There is no `fsync`, file locking, unique run identifier, or tool-execution journal. Interruption can occur after a side effect and before its result record. Recovery does not provide exactly-once execution.

Priority improvements are unique IDs, invalid-tail repair before appending, durable repair records, and tool-call outcome status. Idempotency or state inspection is needed where repeating a command could duplicate side effects.

## Execution results and operational gaps

- **Shell results are mostly unstructured text.** Exit codes are explicitly returned only when output is empty. A failing command that prints text can hide its exit status. Return stdout, stderr, exit code, timeout, and truncation information explicitly.
- **Several output caps apply after collection.** The shell captures complete output before truncation; `read_file` reads the full file before selecting lines. Display caps are not resource limits.
- **Success is inferred from control flow.** Headless mode returns zero when `run()` returns; fleet jobs receive `ok=True` when they do not raise. Neither certifies correctness or passing tests. Add explicit completion criteria where callers need them.
- **Observability is minimal.** Events offer useful hooks but lack durable run/tool IDs, timestamps, approval audit records, aggregate cost, and parent/child correlation. Child transcripts are not persisted by default.
- **Terminal behavior needs polish.** Interactive mode prints final text through the event callback and again through `print(agent.run(task))`. Error handling differs from headless execution.
- **Distribution is undeclared.** There is no `pyproject.toml`, installed entry point, supported Python range, or committed CI workflow. Preserve the capitalized package name.

These gaps do not prevent useful local experiments. They matter when Sthenos becomes an unattended dependency or manages valuable shared projects.

## What was verified

Verification used Python **3.12.14** and did not call the live model API.

| Check | Result | What it establishes |
| --- | --- | --- |
| `python -m tests` | **124 test functions passed.** | Existing coverage of tools, policy, memory, skills, context, sessions, delegation, harness wiring, fleet, and CLI. |
| Product verification script | All existing checks passed. | Committed examples meet their current mechanical checks. |
| Taskman subprocess suite | **18 tests passed.** | Tested CLI command flows and errors work. |
| `python -m Sthenos --help` | Passed. | Documented entry point and option names are valid. |
| Temporary symlink probe | `read_file` blocked; `grep` read the target. | Confirms inconsistent containment. |
| Torn-log resume/run/reload probe | Continuation absent on reload. | Confirms the invalid-tail append limitation. |
| Same-second session probe | Identical labels produced identical paths. | Confirms filename collisions. |

Harness tests fake provider calls where needed. They do not establish live model compatibility, agent task quality, comparative performance, or resilience at every interruption point. HTML checks use text markers and word counts; browser interactions and visual quality were not verified. Historical product session logs are absent from a fresh clone, so historical turn counts and costs cannot be reconstructed.

Package size was measured over `Sthenos/*.py`: **14 files, 1,287 physical lines, 677 implementation lines**. Implementation lines here means nonblank lines excluding standalone comments and AST-identified module/class/function docstrings, not a count of statements or the entire repository. Tests, demos, products, and documentation are excluded.

## Recommended development priorities

These are proposed next steps, not implemented features or delivery estimates.

| Priority | Work | Acceptance evidence |
| --- | --- | --- |
| 1 | Repair damaged-log continuation, persist recovery events, and use unique session IDs. | Repeated load/resume/append/reload after interruptions preserves later history and accurately labels uncertain outcomes. |
| 1 | Apply consistent file checks and offer an isolated backend for untrusted projects. | All file paths pass traversal/symlink checks; host-file and network isolation are verified independently of regexes. |
| 2 | Add tool permission metadata and propagate intended custom tools to children. | Skill reads and custom-tool decisions follow metadata; delegated capabilities have explicit access rules. |
| 2 | Return structured execution results and handle interrupted commands explicitly. | Callers and the model see failures, timeouts, partial output, and uncertain side effects. |
| 2 | Make provider/context limits explicit and test transport/response behavior. | Wire fixtures, stop-reason handling, retry tests, oversized-context checks, and a documented live smoke test. |
| 3 | Add run IDs, child correlation, aggregate usage, and optional spending limits. | All model calls, including compaction and children, can be traced and accounted for. |
| 3 | Package the project and add CI on declared Python/platform versions. | Installation and CLI work in a clean environment; offline tests run on each change. |
| 4 | Extend fleet coordination for demonstrated use cases. | Concurrent writers use independent workspaces or explicit conflict control and acceptance checks. |

For a financial or regulatory agent, the extension point is `extra_tools`: deterministic calculation engines, source-linked rule lookup, reconciliation checks, and report generation can become validated tools. Memory and skills can hold conventions and review instructions. These capabilities require separate implementation and testing; the repository does not supply them today.

The most defensible public description is: **“Sthenos is a compact Python coding-agent harness with direct model integration, local tools, policy checks, persistent conversations, project memory, reusable skills, child agents, and concurrent job execution.”** Its value is control and inspectability of the runtime; the next stage is stronger correctness, recovery, and execution isolation.
