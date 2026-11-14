#!/usr/bin/env bash
# fetch_sonar_gate.sh — fetch the Quality Gate status for a PR, emitting only
# the FAILING conditions as JSON.
#
# Usage:
#   fetch_sonar_gate.sh <pr_number> [project_key]
#
# Output: JSON array of failing gate conditions, each:
#   { "metricKey": "...", "status": "ERROR", "actualValue": "...",
#     "errorThreshold": "...", "comparator": "GT" }
#
# Quality-gate failures (e.g. new-code duplication %, new-code coverage %)
# often do NOT appear as individual issues in `sonar list issues`, so they
# must be surfaced separately from the issue list.
#
# Exits: 0 on success (array may be empty), 1 usage / jq missing,
#        2 CLI missing, 3 auth failure, 4 project key not determinable,
#        5 API error.

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

RESP=$(sonar api get "/api/qualitygates/project_status?projectKey=${PROJECT_KEY}&pullRequest=${PR}" 2>/dev/null) || {
  echo "ERROR: Quality gate API call failed." >&2
  exit 5
}

echo "$RESP" | jq '[.projectStatus.conditions[] | select(.status != "OK")]'
