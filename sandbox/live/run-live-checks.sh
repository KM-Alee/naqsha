#!/usr/bin/env bash
# Manual live OpenAI + CLI smoke. Costs API usage; uses sandbox/live/workspace as tool_root.
#
# Usage:
#   ./run-live-checks.sh          # approval-gated writes/shell (safe default)
#   ./run-live-checks.sh full     # auto_approve profile — can mutate workspace, run shell, etc.
#
# Note: uv run --directory REPO sets cwd to REPO_ROOT, so --profile must be an absolute path.
set -euo pipefail

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "error: export OPENAI_API_KEY first." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORKSPACE="$SCRIPT_DIR/workspace"

MODE="${1:-safe}"
if [[ "$MODE" == "full" ]]; then
  PROFILE_FILE="openai-live-auto.json"
  echo "WARNING: full mode uses auto_approve — high-risk tools can run without prompts." >&2
  echo "         tool_root is sandbox/live/workspace only — keep it disposable." >&2
  echo >&2
else
  PROFILE_FILE="openai-live.json"
fi

PROFILE_ABS="$SCRIPT_DIR/profiles/$PROFILE_FILE"
if [[ ! -f "$PROFILE_ABS" ]]; then
  echo "error: profile missing: $PROFILE_ABS" >&2
  exit 1
fi

mkdir -p "$WORKSPACE"
# Known content for read_file smoke (tracked in git as read-smoke.txt).
if [[ ! -f "$WORKSPACE/read-smoke.txt" ]]; then
  printf '%s\n' 'NAQSHA_LIVE_READ_SMOKE' >"$WORKSPACE/read-smoke.txt"
fi

NAQSHA=(uv run --directory "$REPO_ROOT" naqsha)

echo "== 0) Sanity: policy + tools (no model HTTP yet) =="
"${NAQSHA[@]}" inspect-policy --profile "$PROFILE_ABS" | head -n 8
echo
"${NAQSHA[@]}" tools list --profile "$PROFILE_ABS" | head -n 25

echo
echo "== 1) Live model only (human answer) =="
"${NAQSHA[@]}" run --profile "$PROFILE_ABS" --human \
  'Reply with exactly one word: OK'

echo
echo "== 2) Tool: clock (read-only) =="
"${NAQSHA[@]}" run --profile "$PROFILE_ABS" --human --no-hint \
  'Call the clock tool once and summarise the UTC output in one short sentence.'

echo
echo "== 3) Tool: calculator (read-only) =="
"${NAQSHA[@]}" run --profile "$PROFILE_ABS" --human --no-hint \
  'Use the calculator tool: compute 17 * 23 and state the integer result only (391).'

echo
echo "== 4) Tool: read_file (read-only) =="
"${NAQSHA[@]}" run --profile "$PROFILE_ABS" --human --no-hint \
  'Use read_file once on path read-smoke.txt. Your answer must contain the exact substring NAQSHA_LIVE_READ_SMOKE.'

echo
echo "== 5) Tool: human_approval (read-only) =="
"${NAQSHA[@]}" run --profile "$PROFILE_ABS" --human --no-hint \
  'Call the human_approval tool once with reason live-smoke-check. Then reply with exactly: RECORDED.'

if [[ "$MODE" == "full" ]]; then
  echo
  echo "== 6) Tool: write_file (write tier; auto_approve) =="
  "${NAQSHA[@]}" run --profile "$PROFILE_ABS" --human --no-hint \
    'Use write_file to create hello-live.txt in tool_root with one line: naqsha-live-smoke'

  echo
  echo "== 7) Tool: run_shell (high tier; auto_approve) =="
  "${NAQSHA[@]}" run --profile "$PROFILE_ABS" --human --no-hint \
    'Use run_shell once with argv ["/bin/sh","-c","echo naqsha-shell-ok"], cwd ".", then state whether stdout contained naqsha-shell-ok.'
fi

echo
echo "== 8) QAOA Trace: replay latest (summary) =="
"${NAQSHA[@]}" replay --profile "$PROFILE_ABS" --latest --human

echo
echo "== 9) Eval save + check (may no-op if mismatch) =="
RUN_LINE="$("${NAQSHA[@]}" replay --profile "$PROFILE_ABS" --latest 2>/dev/null | head -n 1)"
RUN_ID="$(python -c 'import json,sys; print(json.loads(sys.stdin.read())["run_id"])' <<<"$RUN_LINE")"
"${NAQSHA[@]}" eval save --profile "$PROFILE_ABS" "$RUN_ID" live-smoke || true
"${NAQSHA[@]}" eval check --profile "$PROFILE_ABS" "$RUN_ID" --name live-smoke || true

echo
echo "Done. Traces: $SCRIPT_DIR/.naqsha/traces/"
