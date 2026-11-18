#!/usr/bin/env bash
# _sonar_common.sh — shared Sonar CLI prerequisite checks and project-key
# resolution. Source this from fetch_sonar.sh and fetch_sonar_gate.sh.
#
# Requires:
#   $PROJECT_KEY — optional; if empty, auto-discovered from origin
#
# On success, sets PROJECT_KEY to the resolved value.
#
# Exit codes (propagate to caller):
#   1 — jq missing
#   2 — sonar CLI missing
#   3 — sonar not authenticated
#   4 — project key could not be determined
#   5 — `sonar list projects` failed, or a list response has no usable paging
#
# Also defines sonar_has_next_page <response-json> <requested-page>.

if ! command -v sonar >/dev/null 2>&1; then
  echo "ERROR: 'sonar' CLI not found on PATH." >&2
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq is required." >&2
  exit 1
fi

if ! sonar auth status >/dev/null 2>&1; then
  echo "ERROR: sonar CLI is not authenticated. Run 'sonar auth login'." >&2
  exit 3
fi

# `sonar list issues` prints only pageIndex, pageSize and total under .paging;
# `list projects` adds hasNextPage, so derive it for both. Exits 5 on paging that
# is missing, which would end the fetch early, or that is not for the requested
# page or has no page size, which would never end it.
sonar_has_next_page() {
  local next
  # jq exits 0 and prints nothing for an empty response, so read the answer, not the status.
  next=$(jq --argjson page "$2" '.paging | [.pageIndex, .pageSize, .total]
    | if all(type == "number") and .[0] == $page and .[1] > 0
      then .[0] * .[1] < .[2] else error("unusable paging") end' <<<"$1") || next=""
  case "$next" in
    true) return 0 ;;
    false) return 1 ;;
  esac
  echo "ERROR: Sonar response has no usable paging for page $2; cannot tell whether more pages exist." >&2
  exit 5
}

if [[ -z "$PROJECT_KEY" ]]; then
  ORIGIN=$(git remote get-url origin 2>/dev/null || true)
  REPO_NAME=$(echo "$ORIGIN" |
    sed -E 's#\.git$##' |
    sed -E 's#.*[:/]##')

  if [[ -z "$REPO_NAME" ]]; then
    echo "ERROR: could not derive repo name from origin; pass project_key explicitly." >&2
    exit 4
  fi

  PROJECT_PAGES=""
  PAGE=1
  while :; do
    RESP=$(sonar list projects --query "$REPO_NAME" --page "$PAGE" --page-size 500) || {
      echo "ERROR: 'sonar list projects' failed for query=$REPO_NAME page=$PAGE" >&2
      exit 5
    }
    PROJECT_PAGES+="${RESP}"$'\n'
    sonar_has_next_page "$RESP" "$PAGE" || break
    PAGE=$((PAGE + 1))
  done
  PROJECTS=$(jq -s '{projects: (map(.projects) | add)}' <<<"$PROJECT_PAGES")
  MATCHES=$(echo "$PROJECTS" | jq --arg n "$REPO_NAME" '[.projects[] | select(.name==$n or (.key|endswith("_"+$n)) or (.key|endswith(":"+$n)))]')
  MATCH_COUNT=$(echo "$MATCHES" | jq 'length')

  if [[ "$MATCH_COUNT" == "0" ]]; then
    FIRST=$(echo "$PROJECTS" | jq -r '.projects[0].key // empty')
    TOTAL=$(echo "$PROJECTS" | jq '.projects | length')
    if [[ "$TOTAL" == "1" && -n "$FIRST" ]]; then
      PROJECT_KEY="$FIRST"
    else
      echo "ERROR: could not uniquely identify Sonar project for repo '$REPO_NAME' (matched $TOTAL)." >&2
      echo "Pass project_key explicitly. Known candidates:" >&2
      echo "$PROJECTS" | jq -r '.projects[] | "  - \(.key)  (\(.name))"' >&2
      exit 4
    fi
  elif [[ "$MATCH_COUNT" == "1" ]]; then
    PROJECT_KEY=$(echo "$MATCHES" | jq -r '.[0].key')
  else
    echo "ERROR: multiple Sonar projects match '$REPO_NAME':" >&2
    echo "$MATCHES" | jq -r '.[] | "  - \(.key)  (\(.name))"' >&2
    echo "Pass project_key explicitly." >&2
    exit 4
  fi
fi
