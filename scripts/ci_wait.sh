#!/usr/bin/env bash
# ci_wait.sh — poll `gh pr checks` until checks conclude. Concludes as soon as
# any check fails (exit 1) so a failure is surfaced even while other checks are
# still pending; otherwise waits until no checks are pending (exit 0).
#
# Usage:
#   ci_wait.sh [--repo <owner>/<repo>] <pr_number> [timeout_seconds] [interval_seconds]
#
# If --repo is omitted, `gh` derives it from the current repo's `origin`.
#
# Exit codes:
#   0 — all checks passed (or only skipped)
#   1 — at least one check in bucket 'fail' or 'cancel'
#   2 — timed out waiting for checks to conclude
#   3 — usage error, or not in a git repo and no --repo given
#   4 — no checks ever registered (5 consecutive empty polls)
#   5 — `gh` call failed (non-empty stderr); see message on stderr
#
# Writes JSON of the final check list (or error summary) to
# <git-dir>/pr-loop/last_ci_status.json when run inside a git repo.

set -euo pipefail

REPO_FLAG=()
if [[ "${1:-}" == "--repo" ]]; then
  if [[ $# -lt 2 ]]; then
    echo "ERROR: --repo requires an argument." >&2
    exit 3
  fi
  REPO_FLAG=(--repo "$2")
  shift 2
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 [--repo <owner>/<repo>] <pr_number> [timeout_seconds] [interval_seconds]" >&2
  exit 3
fi

PR="$1"
TIMEOUT="${2:-1800}"
INTERVAL="${3:-20}"
MAX_EMPTY_POLLS=5

START=$(date +%s)

SUMMARY_FILE=""
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  GIT_DIR=$(git rev-parse --git-dir)
  mkdir -p "${GIT_DIR}/pr-loop"
  SUMMARY_FILE="${GIT_DIR}/pr-loop/last_ci_status.json"
elif [[ ${#REPO_FLAG[@]} -eq 0 ]]; then
  echo "ERROR: not inside a git repository and no --repo given." >&2
  exit 3
fi

write_summary() {
  [[ -n "$SUMMARY_FILE" ]] || return 0
  printf '%s' "$1" >"$SUMMARY_FILE"
}

empty_polls=0

GH_ERR=$(mktemp)
trap 'rm -f "$GH_ERR"' EXIT

while true; do
  NOW=$(date +%s)
  ELAPSED=$((NOW - START))
  if ((ELAPSED > TIMEOUT)); then
    echo "CI wait timed out after ${TIMEOUT}s" >&2
    write_summary '{"status":"timeout"}'
    exit 2
  fi

  if ! RAW=$(gh pr checks "$PR" ${REPO_FLAG[@]+"${REPO_FLAG[@]}"} --json name,state,bucket,link 2>"$GH_ERR"); then
    ERR_TEXT=$(cat "$GH_ERR")
    # `gh pr checks` exits non-zero when at least one check is failing, but still prints JSON.
    # Distinguish by checking whether RAW parses as JSON.
    if [[ -n "${RAW:-}" ]] && echo "${RAW:-}" | jq -e . >/dev/null 2>&1; then
      : # continue — treat as normal output below
    elif printf '%s' "$ERR_TEXT" | grep -qi 'no checks reported'; then
      # `gh pr checks` exits non-zero with an empty stdout and a "no checks
      # reported on the '<branch>' branch" stderr when the PR has zero checks.
      # That is not a gh error — feed it into the empty-poll path so the
      # documented "no checks registered" exit (4) can fire instead of a
      # spurious gh_error exit (5).
      RAW="[]"
    else
      echo "ERROR: gh pr checks failed:" >&2
      echo "$ERR_TEXT" >&2
      write_summary "$(jq -n --arg e "$ERR_TEXT" '{status:"gh_error", error:$e}')"
      exit 5
    fi
  fi

  if [[ -z "${RAW:-}" || "$RAW" == "[]" ]]; then
    empty_polls=$((empty_polls + 1))
    if ((empty_polls >= MAX_EMPTY_POLLS)); then
      echo "ERROR: no checks registered after ${empty_polls} consecutive polls." >&2
      write_summary '{"status":"no_checks"}'
      exit 4
    fi
    echo "No checks registered yet; waiting... (${empty_polls}/${MAX_EMPTY_POLLS})"
    sleep "$INTERVAL"
    continue
  fi
  empty_polls=0

  PENDING=$(echo "$RAW" | jq '[.[] | select(.bucket=="pending")] | length')
  FAILED=$(echo "$RAW" | jq '[.[] | select(.bucket=="fail" or .bucket=="cancel")] | length')
  TOTAL=$(echo "$RAW" | jq 'length')

  echo "CI: total=$TOTAL pending=$PENDING failed=$FAILED (${ELAPSED}s elapsed)"

  # Conclude on failure regardless of pending checks: a perpetually-pending
  # check must not mask a real failure into a timeout (CI_STUCK). The failure
  # is surfaced now for conversion to a fixable blocker; remaining checks are
  # re-evaluated next iteration after the fix is pushed.
  if ((FAILED > 0)); then
    write_summary "$RAW"
    echo "CI concluded with $FAILED failed checks:"
    echo "$RAW" | jq -r '.[] | select(.bucket=="fail" or .bucket=="cancel") | "  - \(.name) [\(.bucket)] \(.link)"' >&2
    exit 1
  fi

  if ((PENDING == 0)); then
    write_summary "$RAW"
    echo "CI concluded: all checks passed."
    exit 0
  fi

  sleep "$INTERVAL"
done
