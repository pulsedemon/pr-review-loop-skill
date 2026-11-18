#!/usr/bin/env bash
# fetch_sonar.sh — list SonarCloud/SonarQube issues for a PR as a JSON array.
#
# Usage:
#   fetch_sonar.sh <pr_number> [project_key]
#
# If <project_key> is omitted, the script discovers it from the current git
# repo's `origin` URL (last path segment) via `sonar list projects --query <repo>`.
# If multiple projects match, pass <project_key> explicitly.
#
# Output: JSON array of issue objects on stdout. The `component` field has the
# leading "<project_key>:" prefix stripped so it's a usable repo-relative path.
#
# Exits:
#   0 — issues fetched (array may be empty)
#   1 — usage error, or `jq` not installed (setup bug, fail fast)
#   2 — `sonar` CLI not installed
#   3 — `sonar` CLI not authenticated (run `sonar auth login`)
#   4 — project key could not be determined (pass explicitly)
#   5 — API call failed

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <pr_number> [project_key]" >&2
  exit 1
fi

PR="$1"
PROJECT_KEY="${2:-}"

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/_sonar_common.sh
. "${HERE}/_sonar_common.sh"

PAGE=1
BATCHES=""
while :; do
  RESP=$(sonar list issues \
    --project "$PROJECT_KEY" \
    --pull-request "$PR" \
    --page "$PAGE" \
    --page-size 500) || {
    echo "ERROR: 'sonar list issues' failed for project=$PROJECT_KEY pr=$PR page=$PAGE" >&2
    exit 5
  }

  # Pages reach jq on stdin: one page of issues can exceed the size limit on a
  # single argument.
  BATCH=$(jq -c --arg p "${PROJECT_KEY}:" '
    [.issues[] | . + {component: (.component | sub("^" + $p; ""))}]
  ' <<<"$RESP") || {
    echo "ERROR: unreadable 'sonar list issues' response for project=$PROJECT_KEY pr=$PR page=$PAGE" >&2
    exit 5
  }
  BATCHES+="${BATCH}"$'\n'

  sonar_has_next_page "$RESP" "$PAGE" || break
  PAGE=$((PAGE + 1))
done

jq -s 'add' <<<"$BATCHES"
