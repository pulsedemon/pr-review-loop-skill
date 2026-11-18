#!/usr/bin/env bash
# fetch_pr.sh: prepare the CURRENT repo to work on a PR.
# Usage: fetch_pr.sh <owner> <repo> <pr_number>
#
# Behavior:
#   - Must be run inside a clean git working tree.
#   - Verifies `origin` remote matches <owner>/<repo>.
#   - fresh runs check out the pr head branch; unfinished resumes never switch or pull.
#   - Fails if there are any uncommitted, staged, or untracked-and-not-gitignored changes.
# Does NOT clone anywhere. Does NOT use /tmp/.
#
# Exits:
#   2: usage error
#   3: not inside a git repo
#   4: no 'origin' remote
#   5: origin remote does not match <owner>/<repo>
#   6: working tree is dirty
#   7: gh CLI missing or older than 2.50.0 (required for `gh pr checks --json`)
#   8: invalid state, or unfinished state for a different pr
#   12: EXTERNAL_PUSH on unsafe resume
#   13: MAX_ITERATIONS on exhausted resume
#   14: SCOPE_SPLIT_RECOMMENDED on recorded scope abort

set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <owner> <repo> <pr_number>" >&2
  exit 2
fi

OWNER="$1"
REPO="$2"
PR="$3"

if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh CLI not installed." >&2
  exit 7
fi

GH_MIN="2.50.0"
GH_VER=$(gh --version 2>/dev/null | head -n1 | awk '{print $3}')
if [[ -z "$GH_VER" ]]; then
  echo "ERROR: could not determine gh version from 'gh --version'." >&2
  exit 7
fi
GH_LOWEST=$(printf '%s\n%s\n' "$GH_MIN" "$GH_VER" | sort -V | head -n1)
if [[ "$GH_LOWEST" != "$GH_MIN" ]]; then
  echo "ERROR: gh $GH_VER is older than required $GH_MIN. 'gh pr checks --json link' is unavailable on older versions, which breaks CI log fetching. Upgrade gh (https://cli.github.com) and retry." >&2
  exit 7
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not inside a git repository." >&2
  exit 3
fi

HERE=$(cd "$(dirname "$0")" && pwd)
cd "$(git rev-parse --show-toplevel)"

ORIGIN_URL=$(git remote get-url origin 2>/dev/null || true)
if [[ -z "$ORIGIN_URL" ]]; then
  echo "ERROR: current repo has no 'origin' remote." >&2
  exit 4
fi

EXPECTED_SLUG="${OWNER}/${REPO}"
ORIGIN_PATH=""
GITHUB_URL_PATTERN='^(https?|ssh|git|git\+ssh|ssh\+git)://([^/@?#]+@)?github\.com/(.+)$'
# match the authority first; a suffix also accepts foreign hosts and paths.
if [[ "$ORIGIN_URL" == git@github.com:* ]]; then
  ORIGIN_PATH="${ORIGIN_URL#git@github.com:}"
elif [[ "$ORIGIN_URL" =~ $GITHUB_URL_PATTERN ]]; then
  ORIGIN_PATH="${BASH_REMATCH[3]}"
fi
if [[ "${ORIGIN_PATH%.git}" != "$EXPECTED_SLUG" ]]; then
  echo "ERROR: origin remote ($ORIGIN_URL) does not match PR repo ($EXPECTED_SLUG)." >&2
  echo "Run this from a checkout of ${EXPECTED_SLUG}." >&2
  exit 5
fi

STATE_FILE="$(git rev-parse --git-dir)/pr-loop/state.json"
RESUMING=false
if [[ -f "$STATE_FILE" ]]; then
  COMPLETED=$(python3 "${HERE}/pr_loop_state.py" completion-marker --state "$STATE_FILE") || exit 8
  # a completed loop's state blocks nothing, whichever pr it was for: state_init.sh replaces it.
  if [[ "$COMPLETED" == false ]]; then
    if ! jq -e --arg owner "$OWNER" --arg repo "$REPO" --arg pr "$PR" '
      .owner == $owner and .repo == $repo and (.pr_number | tostring) == $pr
    ' "$STATE_FILE" >/dev/null; then
      echo "error: invalid state, or an unfinished loop for a different pr: $STATE_FILE" >&2
      exit 8
    fi
    if ! jq -e '.head_branch | type == "string" and length > 0' "$STATE_FILE" >/dev/null; then
      echo "error: state has no recorded head branch" >&2
      exit 8
    fi
    RESUMING=true
  fi
fi

if ! git diff --quiet ||
  ! git diff --cached --quiet ||
  [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
  if [[ "$RESUMING" == true ]]; then
    echo "EXTERNAL_PUSH: working tree has uncommitted changes during resume" >&2
    git status --short >&2
    exit 12
  fi
  echo "ERROR: working tree has uncommitted, staged, or untracked files. Commit, stash, or discard and retry." >&2
  git status --short >&2
  exit 6
fi

if [[ "$RESUMING" == true ]]; then
  # validate before checkout or pull can hide a moved head.
  if [[ "$(git rev-parse --abbrev-ref HEAD)" != "$(jq -r '.head_branch' "$STATE_FILE")" ]]; then
    echo "EXTERNAL_PUSH: current branch differs from the recorded head branch" >&2
    exit 12
  fi
  REMOTE_HEAD=""
  if git fetch origin "refs/pull/${PR}/head" --quiet; then
    REMOTE_HEAD=$(git rev-parse --verify FETCH_HEAD 2>/dev/null || true)
  fi
  DECISION=$(python3 "${HERE}/pr_loop_state.py" resume-decision \
    --state "$STATE_FILE" --current-head "$(git rev-parse HEAD)" \
    --remote-head "$REMOTE_HEAD") || exit 8
  TERMINAL_STATUS=$(jq -r '.terminal_status // empty' <<<"$DECISION")
  if [[ -n "$TERMINAL_STATUS" ]]; then
    echo "$TERMINAL_STATUS: $(jq -r '.reason' <<<"$DECISION")" >&2
    case "$TERMINAL_STATUS" in
      EXTERNAL_PUSH) exit 12 ;;
      MAX_ITERATIONS) exit 13 ;;
      SCOPE_SPLIT_RECOMMENDED) exit 14 ;;
      *) exit 8 ;;
    esac
  fi
fi

if [[ "$RESUMING" == false ]]; then
  git fetch origin --prune --quiet
fi

PR_META=$(gh pr view "$PR" --repo "${OWNER}/${REPO}" --json headRefName,baseRefName --jq '[.headRefName, .baseRefName] | @tsv')
IFS=$'\t' read -r HEAD_BRANCH BASE_BRANCH <<<"$PR_META"

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [[ "$RESUMING" == true ]]; then
  if [[ "$CURRENT_BRANCH" != "$HEAD_BRANCH" ]]; then
    echo "EXTERNAL_PUSH: pr head branch differs from the recorded head branch" >&2
    exit 12
  fi
  echo "resuming '$CURRENT_BRANCH' at its recorded head"
  echo "next iteration: $(jq -r '.next_iteration' <<<"$DECISION")"
elif [[ "$CURRENT_BRANCH" != "$HEAD_BRANCH" ]]; then
  echo "Switching from '$CURRENT_BRANCH' to '$HEAD_BRANCH'..."
  gh pr checkout "$PR" --repo "${OWNER}/${REPO}"
else
  echo "Already on '$HEAD_BRANCH'; fast-forwarding from origin..."
  git pull --ff-only origin "$HEAD_BRANCH"
fi

git fetch origin "$BASE_BRANCH:refs/remotes/origin/${BASE_BRANCH}" --quiet

echo "Ready in: $(git rev-parse --show-toplevel)"
echo "Head branch: $HEAD_BRANCH"
echo "Base: origin/${BASE_BRANCH}"
echo "Head SHA: $(git rev-parse HEAD)"
