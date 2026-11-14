#!/usr/bin/env bash
# fetch_ci_log.sh: fetch the last N lines of the failing log for a named check.
#
# Usage:
#   fetch_ci_log.sh <pr_number> <check_name> [lines]
#
# Defaults: lines=50.
#
# Resolves the run/job IDs from the check's `link` field in `gh pr checks`,
# then invokes `gh run view --log-failed [--job <job_id>]` and tails the
# last <lines> lines. Output goes to stdout; errors to stderr.
#
# requires: gh >=2.50.0 for `gh pr checks --json name,link,bucket`.
#
# Must be run from a checkout of the PR's repository. `gh pr checks` is
# invoked without `--repo`, so it resolves the PR via the current directory's
# git remote. Step 2 of the skill (clean checkout on the PR head branch)
# guarantees this.
#
# Exits:
#   0: log fetched (may be empty if gh produced nothing)
#   1: usage error, or `jq` missing (setup bug, fail fast)
#   2: `gh` CLI missing (CI-tooling class, not a harness bug)
#   3: the check's link could not be parsed into a run ID
#   4: `gh run view` failed
#   5: no failed/cancelled check with the given name, or `gh pr checks`
#       produced no JSON (genuine gh failure; gh's stderr is surfaced)

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <pr_number> <check_name> [lines]" >&2
  exit 1
fi

PR="$1"
CHECK_NAME="$2"
LINES="${3:-50}"

if ! [[ "$LINES" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: lines must be a positive integer, got: $LINES" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq is required." >&2
  exit 1
fi
if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh is required." >&2
  exit 2
fi

GH_ERR=$(mktemp)
trap 'rm -f "$GH_ERR"' EXIT

# retain valid check JSON on gh exit 1 (failed) or 8 (pending).
# surface gh errors when output is empty or invalid; jq alone accepts empty input.
RAW_CHECKS=$(gh pr checks "$PR" --json name,link,bucket 2>"$GH_ERR") || true
if [[ -z "$RAW_CHECKS" ]] || ! printf '%s' "$RAW_CHECKS" | jq -e . >/dev/null 2>&1; then
  echo "ERROR: could not read checks for PR #$PR (gh returned no JSON)." >&2
  cat "$GH_ERR" >&2
  exit 5
fi
LINK=$(printf '%s' "$RAW_CHECKS" |
  jq -r --arg n "$CHECK_NAME" '[.[] | select(.name==$n and (.bucket=="fail" or .bucket=="cancel"))] | .[0].link // empty')

if [[ -z "$LINK" ]]; then
  echo "ERROR: no check named '$CHECK_NAME' found on PR #$PR." >&2
  exit 5
fi

# `link` values look like:
#   https://github.com/owner/repo/actions/runs/<run_id>/job/<job_id>
#   https://github.com/owner/repo/actions/runs/<run_id>
RUN_ID=$(echo "$LINK" | sed -nE 's|.*/runs/([0-9]+)([/?#].*)?$|\1|p')
JOB_ID=$(echo "$LINK" | sed -nE 's|.*/runs/[0-9]+/job/([0-9]+)([/?#].*)?$|\1|p')

if [[ -z "$RUN_ID" ]]; then
  echo "ERROR: could not extract run ID from link: $LINK" >&2
  exit 3
fi

if [[ -n "$JOB_ID" ]]; then
  if ! LOG=$(gh run view "$RUN_ID" --log-failed --job "$JOB_ID" 2>"$GH_ERR"); then
    echo "ERROR: gh run view failed for run=$RUN_ID job=$JOB_ID" >&2
    cat "$GH_ERR" >&2
    exit 4
  fi
else
  echo "WARN: no job ID in check link for '$CHECK_NAME'; returning last $LINES lines across all failed jobs in run $RUN_ID." >&2
  if ! LOG=$(gh run view "$RUN_ID" --log-failed 2>"$GH_ERR"); then
    echo "ERROR: gh run view failed for run=$RUN_ID" >&2
    cat "$GH_ERR" >&2
    exit 4
  fi
fi
printf '%s\n' "$LOG" | tail -n "$LINES"
