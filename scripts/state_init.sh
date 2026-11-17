#!/usr/bin/env bash
# state_init.sh — bootstrap loop state inside <git-dir>/pr-loop/state.json
# Usage: state_init.sh <owner> <repo> <pr_number> [max_iterations] [dry_run]
# Must be run inside a git repo (typically after fetch_pr.sh).
# State is stored under .git/ so it is never tracked by the repo.
#
# Exit codes (per-script ladder; the orchestrator may bucket by script):
#   0  success (state initialized, or unfinished state already exists for this PR)
#   2  usage error (wrong arg count)
#   3  missing dependency (jq not on PATH)
#   4  not inside a git repo
#   5  state file holds an unfinished loop for a different PR
#   6  helper scripts/_adversary_caps.sh missing/unreadable or failed to
#      source (e.g., its preset-value guard tripped because ADVERSARY_CAP
#      was preset to a conflicting value), OR ADVERSARY_CAP
#      (scripts/_adversary_caps.sh) disagrees with schema maximum, OR the
#      schema cap could not be read (jq invocation failed — file missing or
#      malformed JSON — or the path is missing/null/non-numeric)
#   7  gh pr view failed for the given owner/repo/PR

set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <owner> <repo> <pr_number> [max_iterations] [dry_run]" >&2
  exit 2
fi

OWNER="$1"
REPO="$2"
PR="$3"
MAX_ITER="${4:-15}"
DRY_RUN="${5:-false}"
# Reject anything but the two literals. This argument gates the no-write path,
# so treating a typo ("True", "tru") as false would silently enable pushing.
DRY_RUN_FLAG=()
case "$DRY_RUN" in
  true) DRY_RUN_FLAG=(--dry-run) ;;
  false) ;;
  *)
    echo "Usage: $0 <owner> <repo> <pr_number> [max_iterations] [dry_run]" >&2
    echo "  dry_run must be exactly 'true' or 'false' (got '$DRY_RUN')." >&2
    exit 2
    ;;
esac

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq is required." >&2
  exit 3
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not inside a git repository." >&2
  exit 4
fi

HERE=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "${HERE}/.." && pwd)
# Guard helper readability before sourcing. Without this, a missing or
# unreadable _adversary_caps.sh would trip `set -e` on the `.` builtin and
# exit 1 — silently bypassing the documented exit-6 ladder. Surface it as
# exit 6 (the cap-parity bucket) with a remediation hint instead.
HELPER="${HERE}/_adversary_caps.sh"
if [[ ! -r "$HELPER" ]]; then
  echo "ERROR: cannot read ${HELPER}." >&2
  echo "       The helper defining ADVERSARY_CAP is required for the schema parity check." >&2
  exit 6
fi
# Map any helper-sourcing failure (e.g., the preset-value guard at
# _adversary_caps.sh:20-24 returning 1 because ADVERSARY_CAP is preset to a
# conflicting value) onto exit 6 — without this wrapper, `set -e` would
# propagate the helper's exit 1 and bypass the documented exit-6 ladder,
# losing the remediation hint at the failure site.
# shellcheck source=scripts/_adversary_caps.sh
. "$HELPER" || {
  echo "ERROR: failed to source ${HELPER}." >&2
  echo "       If ADVERSARY_CAP was preset in the environment, unset it and retry." >&2
  exit 6
}
CAP_VALUE="${ADVERSARY_CAP:-<unset>}"
# Cross-check ADVERSARY_CAP against BOTH schema maxima at runtime. Reading
# only one would shift the dual-maximum invariant onto a build-time canary
# (scripts/regen_adversary_caps.py writes both maxima from one manifest
# value; tests/bats/test_adversary_cap_behavioral.bats pins behavioral
# parity), but a host checkout running state_init.sh shouldn't depend on
# the bats suite or the generator having been run — read both directly here.
# `jq -r` exits 0 and prints "null" when the path is missing; without the
# `^[0-9]+$` guard the parity check would rubber-stamp a schema where the
# cap field was renamed or removed.
for FIELD in shallow_adversary_runs shallow_approval_adversary_runs; do
  # Capture jq stderr into SCHEMA_CAP so exit 6 owns the "schema unreadable"
  # contract (file missing, malformed JSON, jq absent) rather than letting
  # `set -e` kill the script with no context. The `|| { … }` clause clears
  # `set -e` for the assignment, so the failure-handling branch runs.
  SCHEMA_CAP=$(jq -r ".properties.${FIELD}.maximum" \
    "${REPO_ROOT}/templates/state.schema.json" 2>&1) || {
    echo "ERROR: jq failed to read .properties.${FIELD}.maximum from" >&2
    echo "       ${REPO_ROOT}/templates/state.schema.json: ${SCHEMA_CAP}" >&2
    exit 6
  }
  if [[ ! "$SCHEMA_CAP" =~ ^[0-9]+$ ]]; then
    echo "ERROR: could not read .properties.${FIELD}.maximum from" >&2
    echo "       ${REPO_ROOT}/templates/state.schema.json (got: '$SCHEMA_CAP')." >&2
    echo "       The schema field may have been renamed or removed." >&2
    exit 6
  fi
  if [[ "${ADVERSARY_CAP:-}" != "$SCHEMA_CAP" ]]; then
    echo "ERROR: ADVERSARY_CAP ($CAP_VALUE) disagrees with schema maximum on ${FIELD} ($SCHEMA_CAP)." >&2
    echo "  Fix scripts/_adversary_caps.sh and/or templates/state.schema.json so they agree." >&2
    exit 6
  fi
done

GIT_DIR=$(git rev-parse --git-dir)
STATE_DIR="${GIT_DIR}/pr-loop"
STATE_FILE="${STATE_DIR}/state.json"
TMP_STATE=""

mkdir -p "$STATE_DIR"
cleanup_tmp_state() {
  if [[ -n "${TMP_STATE:-}" && -e "$TMP_STATE" ]]; then
    rm -f "$TMP_STATE"
  fi
}
trap cleanup_tmp_state EXIT

# Resume and refuse exit BEFORE any network call, so a transient gh/auth
# failure cannot mask resumable state with exit 7. gh pr view runs only on the
# fresh-init path below: no state file, or a completed one just removed.
if [[ -f "$STATE_FILE" ]]; then
  EXISTING_PR=$(jq -r '.pr_number // empty' "$STATE_FILE" 2>/dev/null || echo "")
  COMPLETED_AT=$(jq -r '.completed_at // empty' "$STATE_FILE" 2>/dev/null || echo "")
  if [[ -n "$COMPLETED_AT" ]]; then
    # completed_at is written by write_terminal_metric.sh at Step 5. do not key
    # on status: pr_scope_step.py stores scope_split_recommended before Step 5,
    # and that loop must resume so the split summary still gets posted.
    EXISTING_STATUS=$(jq -r '.status // "unknown"' "$STATE_FILE" 2>/dev/null || echo "unknown")
    echo "Previous loop for PR #${EXISTING_PR} completed (${EXISTING_STATUS}) at ${COMPLETED_AT}; reinitializing."
    rm -f "$STATE_FILE" "${STATE_DIR}/pr-scope.json"
  elif [[ "$EXISTING_PR" == "$PR" ]]; then
    echo "State already exists for PR #$PR at $STATE_FILE"
    # the sidecar alone is not a decision: docs/pr-scope.md decides from
    # pr_scope.user_decision whether to skip, re-plan, or re-emit the abort.
    echo "Resume: apply Step 3.5's resume rules (docs/pr-scope.md), then dispatch per Step 3.6."
    exit 0
  else
    echo "ERROR: $STATE_FILE holds an unfinished loop for a different PR (#$EXISTING_PR)." >&2
    echo "Finish that loop or remove the file first." >&2
    exit 5
  fi
fi

META=$(gh pr view "$PR" --repo "${OWNER}/${REPO}" \
  --json number,title,url,headRefName,baseRefName,headRefOid,body,isDraft,author) || {
  echo "ERROR: gh pr view failed for ${OWNER}/${REPO}#${PR}." >&2
  echo "       Verify the PR number, repo, and that 'gh auth status' is healthy." >&2
  exit 7
}

LOOP_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TMP_STATE=$(mktemp "${STATE_FILE}.tmp.XXXXXX")

python3 "${HERE}/pr_loop_state.py" init-state \
  --owner "$OWNER" \
  --repo "$REPO" \
  --max-iterations "$MAX_ITER" \
  ${DRY_RUN_FLAG[@]+"${DRY_RUN_FLAG[@]}"} \
  --started-at "$LOOP_STARTED_AT" \
  --meta-json "$META" >"$TMP_STATE"
mv "$TMP_STATE" "$STATE_FILE"
TMP_STATE=""

echo "Initialized $STATE_FILE"
