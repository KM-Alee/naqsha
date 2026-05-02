# Run Profiles and CLI

This guide describes **Run Profiles** (how **NAQSHA** configures a run) and the **Agent Workbench** command-line interface that drives the **Core Runtime**. It uses project vocabulary from `CONTEXT.md`: **QAOA Trace**, **Tool Policy**, **Approval Gate**, **Memory Port**, **Budget Limit**, **Observation Sanitizer**, and **Reflection Patch**.

---

## Run Profile: what it is

A **Run Profile** is an explicit, named configuration: model adapter, allowed tools, trace location, memory adapter, budgets, and approval behavior. Profiles are JSON or TOML objects validated by the runtime—there is no hidden “only environment variables” configuration path for these choices.

---

## Resolution order (`--profile PATH_OR_NAME`)

When you pass `--profile SPEC`, `load_raw_profile` resolves `SPEC` in this order (first match wins):

1. **Filesystem path**  
   If `SPEC` expands to an existing file (after `Path.expanduser()`), that `.json` or `.toml` file is loaded. Relative paths are resolved from the process current working directory.

2. **Short name under project directories** (current working directory = “project root” for resolution):
   - `profiles/<name>.json` then `profiles/<name>.toml`
   - `.naqsha/profiles/<name>.json` then `.naqsha/profiles/<name>.toml`
   - `examples/profiles/<name>.json` then `examples/profiles/<name>.toml`
   - `docs/examples/profiles/<name>.json` then `docs/examples/profiles/<name>.toml`

3. **Bundled names**  
   Built-in files shipped in the `naqsha` package under `naqsha.bundled_profiles` (for example `local-fake`). For bundled profiles, relative paths inside the profile resolve against the **current working directory**, not a profile file directory.

**Relative paths inside a profile** (`trace_dir`, `tool_root`, `memory_cross_database`) are resolved relative to the **directory containing the profile file**. For bundled profiles, they resolve from **cwd**.

The CLI default is `--profile local-fake` if you omit the flag.

---

## Run Profile fields (reference)

Top-level keys must match the schema below; unknown keys are rejected.

| Field | Type | Semantics |
|-------|------|-----------|
| `name` | string | Display or diagnostic name (default `unnamed` if missing). |
| `model` | string | Model client: `fake`, `openai_compat`, `anthropic`, `gemini`. Hyphens in the file are normalized to underscores. |
| `trace_dir` | string (path) | **Trace Store** directory for **QAOA Trace** JSONL files (default `.naqsha/traces`). |
| `tool_root` | string (path) | Working-directory root for tools that need filesystem context (default `.`). |
| `allowed_tools` | `null` or array of strings | `null`: all **Starter Tool Set** names are allowed. Non-empty array: only listed tools (each must be a known starter tool name). |
| `memory_adapter` | string | `none`, `inmemory`, or `simplemem_cross`. |
| `memory_token_budget` | integer ≥ 1 | Budget for material injected from the **Memory Port** into prompts (default `512`). |
| `memory_cross_project` | string | SimpleMem-Cross project label (default `default`). |
| `memory_cross_database` | string (path) | SQLite path for `simplemem_cross` (default `.naqsha/simplemem-cross.sqlite`). |
| `auto_approve` | boolean | When `true`, the **Approval Gate** does not block; all policy-approved tool calls run without interactive approval (default `false`). |
| `approval_required_tiers` | array of strings or omitted | **Risk tiers** that require approval when `auto_approve` is `false` (default `["write", "high"]`). Must be non-empty if present. |
| `budgets` | object | **Budget Limits** (see below). Omitted fields use library defaults. |
| `sanitizer_max_chars` | integer ≥ 1 | Max characters passed through the **Observation Sanitizer** per observation (default `4000`). |
| `fake_model` | object | **Only** when `model` is `fake`. Scripted **NAP** turns. Contains `messages`: `null`/omitted for built-in default script, or an array of validated NAP-shaped objects. |
| `openai_compat` | object | **Only** when `model` is `openai_compat`. See nested section below. |
| `anthropic` | object | **Only** when `model` is `anthropic`. See nested section below. |
| `gemini` | object | **Only** when `model` is `gemini`. See nested section below. |

### `budgets` object

| Key | Type | Default (if omitted) | Semantics |
|-----|------|----------------------|-----------|
| `max_steps` | int ≥ 1 | `8` | Hard cap on agent steps. |
| `max_tool_calls` | int ≥ 1 | `16` | Hard cap on tool invocations. |
| `wall_clock_seconds` | number > 0 | `30` | Wall-clock budget for the run. |
| `per_tool_seconds` | number > 0 | `5` | **Tool Scheduler** timeout per tool call when a budget meter is enforced. |
| `max_model_tokens` | int ≥ 1 or `null` | `null` | Optional model token cap; `null` means unset. |

Exhausted **Budget Limits** fail closed (not advisory).

### `openai_compat` (Chat Completions–style HTTP client)

| Key | Type | Default |
|-----|------|---------|
| `base_url` | string | `https://api.openai.com/v1` |
| `model` | string | `gpt-4o-mini` |
| `api_key_env` | string | `OPENAI_API_KEY` |
| `timeout_seconds` | number > 0 | `120` |

Use `base_url` for OpenAI-compatible gateways (point at the server’s `/v1` root).

### `anthropic` (Messages API)

| Key | Type | Default |
|-----|------|---------|
| `base_url` | string | `https://api.anthropic.com` |
| `model` | string | `claude-sonnet-4-20250514` |
| `api_key_env` | string | `ANTHROPIC_API_KEY` |
| `timeout_seconds` | number > 0 | `120` |
| `max_tokens` | int ≥ 1 | `4096` |
| `anthropic_version` | string | `2023-06-01` |

### `gemini` (`generateContent`)

| Key | Type | Default |
|-----|------|---------|
| `base_url` | string | `https://generativelanguage.googleapis.com` |
| `model` | string | `gemini-2.0-flash` |
| `api_key_env` | string | `GEMINI_API_KEY` |
| `timeout_seconds` | number > 0 | `120` |

---

## CLI cheat sheet

Global: `naqsha --version`. Every subcommand that needs a profile accepts:

- `--profile PATH_OR_NAME` (default `local-fake`)
- `--trace-dir PATH` — override `trace_dir`
- `--tool-root PATH` — override `tool_root`
- `--auto-approve` — force `auto_approve` on for this invocation

| Command | Purpose | Notable flags / arguments |
|---------|---------|---------------------------|
| `naqsha init` | Create `.naqsha/` layout and default profile | `--profile-name NAME` (default `workbench` → `.naqsha/profiles/<name>.json`) |
| `naqsha run` | Run a query through the **Core Runtime** | `QUERY`; `--approve-prompt`; `--human`; `--no-hint` |
| `naqsha replay` | Summarize a **QAOA Trace** or re-execute with stored observations | `[RUN_ID]`; `--latest`; `--re-execute`; `--approve-prompt` (with `--re-execute`); `--human` |
| `naqsha trace inspect` | Same summary path as `replay` without `--re-execute` | `[RUN_ID]`; `--latest`; `--human` |
| `naqsha inspect-policy` | Print resolved profile + **Tool Policy** snapshot (JSON) | profile flags only |
| `naqsha profile show` | Same output as `inspect-policy` | profile flags only |
| `naqsha tools list` | JSON list of allowed tools and risk metadata for the profile | profile flags only |
| `naqsha eval save` | Save regression fixture from a trace | `RUN_ID` `NAME`; `--output PATH` |
| `naqsha eval check` | Compare trace to fixture and re-execute | `RUN_ID`; `--name FIXTURE` or `--fixture PATH`; `--approve-prompt` |
| `naqsha reflect` | Build isolated **Reflection Patch** workspace (+ reliability gate) | `RUN_ID`; `--workspace-base PATH` |
| `naqsha improve` | Same as `reflect` (alias; includes review-oriented messaging) | `RUN_ID`; `--workspace-base PATH` |

**`replay` / `trace inspect` / `eval check` identity:** `RUN_ID` is optional when `--latest` selects the newest trace file under `trace_dir` (by modification time).

**Exit hints:** On successful `run`, the CLI prints a replay hint to stderr unless `--no-hint`.

---

## Tool Policy and Approval Gate

- **Tool Policy** decides which tools are **Allowed Tools** for the run and which calls are subject to approval (by **risk tier**).
- The **Approval Gate** is the checkpoint that requires explicit human approval (CLI: stdin prompt) before executing calls that policy marks as needing approval.

**Risk tiers** (from the **Starter Tool Set** metadata): `read_only`, `write`, `high`.

- Default **`approval_required_tiers`**: `write` and `high`. `read_only` tools typically do not require approval unless you change this list.
- **`auto_approve`**: When `true` (in the profile or via `--auto-approve`), approval prompts are skipped; policy still applies to what is allowed.
- **`--approve-prompt`**: Uses `InteractiveApprovalGate`—you confirm each approval-required tool on stdin. Ignored when `auto_approve` is true.
- **`--auto-approve` CLI flag** overrides the profile and sets `auto_approve` to `true` for that process.

---

## Security: API keys and secrets

- Run Profiles store **only environment variable names** for credentials (`api_key_env`), never secret values.
- Export keys in your shell or secret manager; do not commit API keys or tokens into profile files or the repo.
- The **Observation Sanitizer** limits what reaches **QAOA Traces**, the **Memory Port**, and prompts; tune `sanitizer_max_chars` alongside policy, not as a substitute for keeping secrets out of tool outputs.

---

## Example: minimal remote-model profile

Profiles may be **JSON** or **TOML**. Optional keys are shown below only as `#` comments (no secret values—only env var **names** appear in real profiles).

**TOML** (comments are valid; uncomment sections you need):

```toml
# name = "string — label for this profile"
# model = "openai_compat" | "anthropic" | "gemini"
# trace_dir = "relative or absolute path — QAOA Trace directory"
# tool_root = "relative or absolute path — tool cwd root"
# allowed_tools = null or ["tool_a", "tool_b"]
# memory_adapter = "none" | "inmemory" | "simplemem_cross"
# memory_token_budget = 512
# memory_cross_project = "default"
# memory_cross_database = ".naqsha/simplemem-cross.sqlite"
# auto_approve = false
# approval_required_tiers = ["write", "high"]
# sanitizer_max_chars = 4000
# [budgets]
# max_steps = 8
# max_tool_calls = 16
# wall_clock_seconds = 30.0
# per_tool_seconds = 5.0
# max_model_tokens = null

name = "example-remote"
model = "openai_compat"
trace_dir = ".naqsha/traces"
tool_root = "."

# [openai_compat]
# base_url = "https://api.openai.com/v1"
# model = "gpt-4o-mini"
# api_key_env = "OPENAI_API_KEY"
# timeout_seconds = 120.0

# For anthropic / gemini, set model and use [anthropic] or [gemini]
# with the fields from the reference table above.
```

**JSON** (strict; `openai_compat` omitted → defaults, including `api_key_env` = `OPENAI_API_KEY`):

```json
{
  "name": "example-remote",
  "model": "openai_compat",
  "trace_dir": ".naqsha/traces",
  "tool_root": "."
}
```

---

## See also

- `examples/profiles/README.md` — copy-paste examples and remote adapter table
- Bundled reference profile: `local-fake` (package `naqsha.bundled_profiles`)
