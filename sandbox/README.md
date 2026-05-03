# NAQSHA Sandbox Testing Environment

This sandbox provides a complete testing environment for NAQSHA V2 with a 3-agent team:
- **Orchestrator**: Coordinates the team using GPT-4o-mini
- **Coder**: Writes code using GPT-4o-mini
- **Code Reviewer**: Reviews code using GPT-4o-mini

## Features Enabled

✅ **Multi-Agent Team** - Orchestrator + 2 workers with tool-based delegation  
✅ **Dynamic Memory Engine** - SQLite with shared/private namespaces  
✅ **Hierarchical QAOA Trace** - Full span attribution across agents  
✅ **Role-Based Tool Policies** - Different tools per agent  
✅ **Circuit Breakers** - Automatic failure handling  
✅ **Budget Limits** - Per-agent step/token/time constraints  
✅ **Reflection Loop** - Code improvement patches (manual review)  

## Quick Start

### 1. Configure Your OpenAI API Key

```bash
./setup.sh
```

This will prompt you for your OpenAI API key and configure the environment.

### 2. Run Automated Test (Snake Game)

```bash
./test_snake_game.sh
```

This will ask the agent team to build a complete snake game in HTML/CSS/JS and save it to `output/`.

### 3. Launch Interactive Mode (Note: Limited functionality)

```bash
./command_center.sh
```

**Note:** The Command Center TUI has limited functionality in the current implementation. For reliable task execution, use `./run_task.sh` instead. See `KNOWN_ISSUES.md` for details.

## Manual Usage

### Run a Custom Task

```bash
# Make sure you've run setup.sh first
source .env
uv run --extra tui naqsha run "Your task here"
```

### Inspect Traces

```bash
# List all traces
ls -la .naqsha/traces/

# View a specific trace
cat .naqsha/traces/<run_id>.jsonl | jq '.'

# See which agents participated
cat .naqsha/traces/<run_id>.jsonl | jq -r '.agent_id' | sort | uniq -c
```

### Browse Memory

```bash
# Open the SQLite database
sqlite3 .naqsha/memory.db

# List all tables
.tables

# View shared memory
SELECT * FROM shared_notes LIMIT 10;

# View agent-specific private memory
SELECT * FROM private_coder_scratch LIMIT 10;
```

### Replay a Trace

```bash
source .env
uv run naqsha replay --latest
```

## Configuration

The team is configured in `naqsha.toml`:

- **Orchestrator** (`orch`): Coordinates tasks, delegates to workers
  - Tools: `clock`, `list_memory_tables`
  - Budget: 20 steps, 40 tool calls, 120s wall time
  
- **Coder** (`coder`): Writes code and manages memory schema
  - Tools: `clock`, `memory_schema`, `list_memory_tables`, `read_file`, `write_file`
  - Budget: 12 steps, 24 tool calls, 90s wall time
  
- **Code Reviewer** (`reviewer`): Reviews code (read-only)
  - Tools: `clock`, `list_memory_tables`, `read_file`
  - Budget: 10 steps, 20 tool calls, 60s wall time

## Architecture

```
Orchestrator (GPT-4o-mini)
    ├─ delegate_to_coder("Write snake game")
    │  └─ Coder (GPT-4o-mini) [child span]
    │     ├─ write_file("snake.html")
    │     ├─ write_file("snake.css")
    │     └─ write_file("snake.js")
    └─ delegate_to_reviewer("Review the code")
       └─ Reviewer (GPT-4o-mini) [child span]
          ├─ read_file("snake.html")
          ├─ read_file("snake.css")
          └─ read_file("snake.js")
```

## Troubleshooting

### "No module named 'naqsha'"

Make sure you're running from the project root (one level up from sandbox/):

```bash
cd ..
uv run --extra tui naqsha run "test"
```

### "OPENAI_API_KEY not set"

Run the setup script:

```bash
./setup.sh
```

### TUI Not Launching

Set the environment variable to force plain output:

```bash
NAQSHA_NO_TUI=1 uv run naqsha run "test"
```

Or install TUI dependencies:

```bash
uv sync --extra tui
```

## Files

- `naqsha.toml` - Team topology configuration
- `.env` - OpenAI API key (created by setup.sh, gitignored)
- `.naqsha/` - Workspace data (traces, memory, profiles)
- `output/` - Generated files from agent tasks
- `setup.sh` - Configure API key
- `test_snake_game.sh` - Automated test script
- `command_center.sh` - Launch interactive TUI

## Next Steps

1. Modify `naqsha.toml` to add more agents or change models
2. Try different tasks in `test_snake_game.sh`
3. Enable embeddings: set `embeddings = true` in `[memory]` section
4. Enable auto-merge: set `auto_merge = true` in `[reflection]` (use with caution!)
5. Add custom tools by creating Python files in the project root

## Safety Notes

⚠️ **Auto-approve is enabled for sandbox testing** - In production, set `auto_approve = false`  
⚠️ **Auto-merge is disabled by default** - Reflection patches require manual review  
⚠️ **Budget limits prevent runaway costs** - Adjust in `naqsha.toml` if needed  
⚠️ **API keys are never stored in config files** - Only environment variable names  

## Documentation

For complete documentation, see:
- `../AGENTS.md` - Development guide
- `../CONTEXT.md` - Glossary and concepts
- `../docs/prd/0002-naqsha-v2-runtime.md` - Architecture PRD
- `../docs/user-guide/` - User guides
