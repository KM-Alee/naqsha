# Example Run Profiles

These JSON files show the supported Run Profile fields for `naqsha run`, `replay`, and `inspect-policy`.

- Copy an example and adapt paths for your workstation.
- The same defaults ship as bundled `local-fake` (built into the `naqsha` package).

After **`naqsha init`**, a profile named **`workbench`** is created under `.naqsha/profiles/`
and may be referenced as **`--profile workbench`** from that project directory.

Resolve paths relative to **the profile file directory** (`trace_dir` and `tool_root`).

## Remote model adapters

Supported `model` values:

| Value | Config section | Default API key env var |
|-------|----------------|-------------------------|
| `openai_compat` | `openai_compat` | `OPENAI_API_KEY` |
| `anthropic` | `anthropic` | `ANTHROPIC_API_KEY` |
| `gemini` | `gemini` | `GEMINI_API_KEY` |

Secrets are never stored in profile files: each section has `api_key_env` naming an environment variable you export locally.

Examples: `openai-compat.example.json`, `anthropic.example.json`, `gemini.example.json`.

OpenAI-compatible gateways (LM Studio, LiteLLM proxy, etc.) use `openai_compat.base_url` pointing at the server's `/v1` root.
