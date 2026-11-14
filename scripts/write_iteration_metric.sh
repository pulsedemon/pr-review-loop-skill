#!/usr/bin/env bash
# write_iteration_metric.sh — emit one iteration metric line.
#
# Reads <git-dir>/pr-loop/state.json and constructs the per-iteration metric
# record from history[-1] + top-level counters, then pipes to
# scripts/append_metric.py (which owns flock + write).
#
# Env (caller-set):
#   OWNER, REPO, PR_NUMBER — PR coordinates.
#
# Exit codes:
#   0   — line appended successfully.
#   2   — usage error (missing env, state file absent, malformed PR_NUMBER),
#         OR state validation error from scripts/pr_loop_state.py
#         (malformed JSON, invalid nested types, bad timestamps/iteration, etc.).
#   Other non-zero — forwarded from append_metric.py. The caller (loop
#   orchestrator) is responsible for logging and continuing per SKILL.md
#   §4i ("a missing metric record is preferable to losing the iteration"),
#   not this script.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
STATE="$(git rev-parse --git-dir)/pr-loop/state.json"

if [[ -z "${OWNER:-}" || -z "${REPO:-}" || -z "${PR_NUMBER:-}" ]]; then
  echo "write_iteration_metric: OWNER/REPO/PR_NUMBER must be set" >&2
  exit 2
fi
if ! [[ "$PR_NUMBER" =~ ^[0-9]+$ ]]; then
  echo "write_iteration_metric: PR_NUMBER must be numeric (got '$PR_NUMBER')" >&2
  exit 2
fi
if [[ ! -f "$STATE" ]]; then
  echo "write_iteration_metric: state file missing at $STATE" >&2
  exit 2
fi

python3 "${HERE}/pr_loop_state.py" iteration-metric \
  --state "$STATE" \
  --owner "$OWNER" \
  --repo "$REPO" \
  --pr-number "$PR_NUMBER" \
  --timestamp "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
  --script-name write_iteration_metric | python3 "${HERE}/append_metric.py"
