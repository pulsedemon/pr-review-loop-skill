#!/usr/bin/env bash
# safe_push.sh: push with hard safety rails.
# Usage: safe_push.sh <head_branch> <expected_remote_sha>
# Must be run from the PR head-branch checkout.
#
# <expected_remote_sha> is the remote head this iteration started from
# (state.json initial_head_sha, or history[-1].head_sha_after). It is required:
# without it the divergence check cannot see a force-push that rewound the
# remote to an ancestor of local HEAD.
#
# Exits:
#   0: pushed
#   2: usage error
#   10: head branch is protected
#   11: current branch is not <head_branch>
#   12: remote moved, diverged, was deleted, or could not be fetched
#   other: git's own status, including a failed push whose remote could not be
#          queried afterwards

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <head_branch> <expected_remote_sha>" >&2
  exit 2
fi

HEAD_BRANCH="$1"
EXPECTED_REMOTE_SHA="$2"

PROTECTED=("main" "master" "develop" "release" "prod" "production")
for p in "${PROTECTED[@]}"; do
  if [[ "$HEAD_BRANCH" == "$p" ]]; then
    echo "REFUSE: head branch '$HEAD_BRANCH' is protected." >&2
    exit 10
  fi
done

CURRENT=$(git rev-parse --abbrev-ref HEAD)
if [[ "$CURRENT" != "$HEAD_BRANCH" ]]; then
  echo "REFUSE: currently on '$CURRENT', expected '$HEAD_BRANCH'." >&2
  exit 11
fi

LOCAL_HEAD=$(git rev-parse --verify 'HEAD^{commit}')

# refuse when the remote state cannot be verified.
if ! git fetch origin "$HEAD_BRANCH" --quiet; then
  echo "REFUSE: could not fetch origin/'$HEAD_BRANCH'; remote state unknown." >&2
  exit 12
fi

REMOTE_HEAD=$(git rev-parse "origin/${HEAD_BRANCH}" 2>/dev/null || echo "")

# An absent remote ref means the branch is gone; pushing would recreate it.
if [[ -z "$REMOTE_HEAD" ]]; then
  echo "REFUSE: remote '$HEAD_BRANCH' has no head; branch deleted or never pushed." >&2
  exit 12
fi

if [[ "$REMOTE_HEAD" != "$EXPECTED_REMOTE_SHA" ]]; then
  echo "REFUSE: remote '$HEAD_BRANCH' moved externally since this iteration started." >&2
  echo "  expected remote: $EXPECTED_REMOTE_SHA" >&2
  echo "  actual remote:   $REMOTE_HEAD" >&2
  exit 12
fi

# a lease permits non-fast-forward updates; prove ancestry for the exact commit pushed.
if ! git merge-base --is-ancestor "$EXPECTED_REMOTE_SHA" "$LOCAL_HEAD"; then
  echo "REFUSE: remote '$HEAD_BRANCH' has diverged or ancestry could not be verified." >&2
  exit 12
fi

echo "Pushing $HEAD_BRANCH -> origin/$HEAD_BRANCH (fast-forward, no force, hooks enabled)..."
if git push --force-with-lease="refs/heads/$HEAD_BRANCH:$EXPECTED_REMOTE_SHA" origin "$LOCAL_HEAD:refs/heads/$HEAD_BRANCH"; then
  exit 0
else
  PUSH_STATUS=$?
fi

REMOTE_HEAD=$(git ls-remote origin "refs/heads/$HEAD_BRANCH") || exit "$PUSH_STATUS"
REMOTE_HEAD=${REMOTE_HEAD%%$'\t'*}
if [[ "$REMOTE_HEAD" != "$EXPECTED_REMOTE_SHA" ]]; then
  echo "REFUSE: remote '$HEAD_BRANCH' moved externally during push." >&2
  exit 12
fi
exit "$PUSH_STATUS"
