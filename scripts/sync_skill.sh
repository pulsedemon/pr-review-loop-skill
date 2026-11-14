#!/usr/bin/env bash
# sync_skill.sh: best-effort fast-forward of the skill install directory.
# Usage: sync_skill.sh
#
# Operates on the skill repo (resolved from this script's location), not the
# user's PR checkout. Always exits 0 unless mis-invoked; pull failures are
# non-fatal for the PR loop. See docs/skill-update.md.

set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

if [[ "${PR_REVIEW_LOOP_SKIP_SKILL_SYNC:-}" == "1" ]]; then
  echo "sync_skill: skipped (PR_REVIEW_LOOP_SKIP_SKILL_SYNC=1)" >&2
  exit 0
fi

cd "$SKILL_ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "sync_skill: not a git repository; skipping" >&2
  exit 0
fi

GIT_ROOT=$(git rev-parse --show-toplevel)
if [[ "$(cd "$GIT_ROOT" && pwd -P)" != "$SKILL_ROOT" ]]; then
  echo "sync_skill: skill root is not the git top-level; skipping" >&2
  exit 0
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "sync_skill: skill repo has local changes; skipping pull" >&2
  exit 0
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)
if [[ "$BRANCH" == "HEAD" ]]; then
  echo "sync_skill: detached HEAD; skipping" >&2
  exit 0
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "sync_skill: no origin remote; skipping" >&2
  exit 0
fi

OLD_SHA=$(git rev-parse HEAD)

if ! git fetch origin --quiet 2>/dev/null; then
  echo "sync_skill: fetch failed; continuing with installed version" >&2
  exit 0
fi

if ! git pull --ff-only --quiet 2>/dev/null; then
  echo "sync_skill: pull failed; continuing with installed version" >&2
  exit 0
fi

NEW_SHA=$(git rev-parse HEAD)
if [[ "$OLD_SHA" != "$NEW_SHA" ]]; then
  echo "sync_skill: updated ${OLD_SHA:0:7} -> ${NEW_SHA:0:7}" >&2
else
  echo "sync_skill: already up to date (${NEW_SHA:0:7})" >&2
fi

exit 0
