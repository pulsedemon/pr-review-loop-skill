#!/usr/bin/env bash
# write_terminal_metric.sh — emit the one-shot terminal-rollup metric line.
#
# Runs once per loop, immediately before the Step 5 exit.
#
# Env (caller-set):
#   TERMINAL_STATUS — uppercase exit status (e.g. SUCCESS, NO_PROGRESS).
#
# Exit codes:
#   0   — state.json marked completed (status + completed_at) and the line appended.
#   2   — usage error (missing env, state file absent),
#         OR state validation error from scripts/pr_loop_state.py
#         (malformed JSON, invalid nested types, bad timestamps/iteration, etc.).
#   Other non-zero — forwarded from append_metric.py. The caller (loop
#   orchestrator) is responsible for logging and continuing per SKILL.md §5
#   ("the comment is the user-visible deliverable and must not be blocked
#   on metric persistence"), not this script.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
STATE="$(git rev-parse --git-dir)/pr-loop/state.json"

if [[ -z "${TERMINAL_STATUS:-}" ]]; then
  echo "write_terminal_metric: TERMINAL_STATUS must be set" >&2
  exit 2
fi
if [[ ! -f "$STATE" ]]; then
  echo "write_terminal_metric: state file missing at $STATE" >&2
  exit 2
fi

STAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# Build the metric line first so a malformed state file still exits 2 unmarked,
# then mark the state before the append: an append failure exits this script,
# and state_init.sh must still see a completed loop on the next run.
METRIC="$(python3 "${HERE}/pr_loop_state.py" terminal-metric \
  --state "$STATE" \
  --terminal-status "${TERMINAL_STATUS}" \
  --timestamp "$STAMP" \
  --script-name write_terminal_metric)"

TMP="$(mktemp "${STATE}.tmp.XXXXXX")"
trap 'rm -f "$TMP"' EXIT
jq --arg s "$(tr '[:upper:]' '[:lower:]' <<<"${TERMINAL_STATUS}")" --arg t "$STAMP" \
  '.status = $s | .completed_at = $t' "$STATE" >"$TMP"
mv "$TMP" "$STATE"

printf '%s\n' "$METRIC" | python3 "${HERE}/append_metric.py"
