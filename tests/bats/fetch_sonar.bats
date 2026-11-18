#!/usr/bin/env bats

load test_helper

setup() {
  make_tmp_repo
}

@test "exits 2 when sonar CLI is missing" {
  assert_sonar_exits_2_missing_cli "fetch_sonar.sh"
}

@test "exits 3 when sonar not authenticated" {
  assert_sonar_exits_3_not_authenticated "fetch_sonar.sh"
}

@test "exits 1 on usage error" {
  assert_sonar_exits_1_usage_error "fetch_sonar.sh"
}

# Serves $SONAR_FIXTURES/<issues|projects>-<page>.json for `sonar list`, fails
# on a page with no fixture, and logs each list call to $SONAR_LOG.
stub_paged_sonar() {
  export SONAR_FIXTURES="${BATS_TEST_TMPDIR}/sonar"
  export SONAR_LOG="${BATS_TEST_TMPDIR}/sonar.log"
  mkdir -p "$SONAR_FIXTURES"
  : >"$SONAR_LOG"
  stub_cmd sonar '[[ "$1 $2" == "auth status" ]] && exit 0
[[ "$1" == "list" ]] || exit 1
kind="$2"
echo "$*" >>"$SONAR_LOG"
page=1
while (($#)); do
  if [[ "$1" == --page ]]; then page="$2"; fi
  shift
done
fixture="${SONAR_FIXTURES}/${kind}-${page}.json"
if [[ ! -f "$fixture" ]]; then
  echo "sonar: server error on page ${page}" >&2
  exit 1
fi
cat "$fixture"'
}

# issues_page <page> <total> <first> <last>: issue keys first..last, in the
# shape `sonar list issues` prints (paging has no hasNextPage).
issues_page() {
  jq -n --argjson page "$1" --argjson total "$2" --argjson first "$3" --argjson last "$4" '{
    total: $total, p: $page, ps: 500,
    paging: {pageIndex: $page, pageSize: 500, total: $total},
    issues: [range($first; $last + 1) | {
      key: tostring, rule: "ts:S1", severity: "MAJOR", type: "BUG", status: "OPEN",
      component: "org_repo:src/a.ts", project: "org_repo", line: .,
      message: ("finding " + ("x" * 2200))
    }]
  }' >"${SONAR_FIXTURES}/issues-$1.json"
}

# projects_page <page> <total> <keys-json>: the shape `sonar list projects`
# prints. Names never equal the repo name, so only key suffixes can match.
projects_page() {
  jq -n --argjson page "$1" --argjson total "$2" --argjson keys "$3" '{
    projects: [$keys[] | {key: ., name: ("name-" + .)}],
    paging: {pageIndex: $page, pageSize: 500, total: $total,
             hasNextPage: ($page * 500 < $total)}
  }' >"${SONAR_FIXTURES}/projects-$1.json"
}

filler_keys() {
  jq -cn --argjson n "$1" '[range($n) | "other_\(.)"]'
}

@test "returns a single page with the project prefix stripped" {
  stub_paged_sonar
  issues_page 1 2 1 2

  bats_require_minimum_version 1.5.0
  run --separate-stderr bash "${SCRIPTS}/fetch_sonar.sh" 42 org_repo
  [[ "$status" -eq 0 ]]
  [[ "$(jq -c '[.[] | [.key, .component]]' <<<"$output")" == '[["1","src/a.ts"],["2","src/a.ts"]]' ]]
  [[ "$(grep -c '^list issues' "$SONAR_LOG")" -eq 1 ]]
}

@test "fetches every issue page when paging has no hasNextPage" {
  stub_paged_sonar
  issues_page 1 501 1 500
  issues_page 2 501 501 501

  bats_require_minimum_version 1.5.0
  run --separate-stderr bash "${SCRIPTS}/fetch_sonar.sh" 42 org_repo
  [[ "$status" -eq 0 ]]
  [[ "$(jq '[.[].key] | unique | length' <<<"$output")" -eq 501 ]]
  [[ "$(jq 'length' <<<"$output")" -eq 501 ]]
  [[ "$(grep -c '^list issues' "$SONAR_LOG")" -eq 2 ]]
  grep -q -- '--page 2 ' "$SONAR_LOG"
}

@test "stops after a page that exactly fills the total" {
  stub_paged_sonar
  issues_page 1 500 1 500

  bats_require_minimum_version 1.5.0
  run --separate-stderr bash "${SCRIPTS}/fetch_sonar.sh" 42 org_repo
  [[ "$status" -eq 0 ]]
  [[ "$(jq 'length' <<<"$output")" -eq 500 ]]
  [[ "$(grep -c '^list issues' "$SONAR_LOG")" -eq 1 ]]
}

@test "exits 5 with no issue array when a later issue page fails" {
  stub_paged_sonar
  issues_page 1 501 1 500

  bats_require_minimum_version 1.5.0
  run --separate-stderr bash "${SCRIPTS}/fetch_sonar.sh" 42 org_repo
  [[ "$status" -eq 5 ]]
  [[ -z "$output" ]]
  [[ "$stderr" == *"server error on page 2"* ]]
  [[ "$stderr" == *"page=2"* ]]
}

@test "exits 5 when an issue page has no paging totals" {
  stub_paged_sonar
  echo '{"issues": []}' >"${SONAR_FIXTURES}/issues-1.json"

  bats_require_minimum_version 1.5.0
  run --separate-stderr bash "${SCRIPTS}/fetch_sonar.sh" 42 org_repo
  [[ "$status" -eq 5 ]]
  [[ -z "$output" ]]
  [[ "$stderr" == *"paging"* ]]
}

@test "exits 5 when a page reports a different page than the one requested" {
  stub_paged_sonar
  issues_page 1 501 1 500
  cp "${SONAR_FIXTURES}/issues-1.json" "${SONAR_FIXTURES}/issues-2.json"

  bats_require_minimum_version 1.5.0
  run --separate-stderr bash "${SCRIPTS}/fetch_sonar.sh" 42 org_repo
  [[ "$status" -eq 5 ]]
  [[ -z "$output" ]]
  [[ "$(grep -c '^list issues' "$SONAR_LOG")" -eq 2 ]]
}

@test "exits 5 when the issues response is not JSON" {
  stub_paged_sonar
  echo 'warning: not json' >"${SONAR_FIXTURES}/issues-1.json"

  bats_require_minimum_version 1.5.0
  run --separate-stderr bash "${SCRIPTS}/fetch_sonar.sh" 42 org_repo
  [[ "$status" -eq 5 ]]
  [[ -z "$output" ]]
  [[ "$stderr" == *"unreadable 'sonar list issues' response"* ]]
}

@test "explicit project key skips project discovery" {
  stub_paged_sonar
  issues_page 1 0 1 0

  run bash "${SCRIPTS}/fetch_sonar.sh" 42 org_repo
  [[ "$status" -eq 0 ]]
  ! grep -q '^list projects' "$SONAR_LOG"
}

@test "exits 4 when a second project match is on a later page" {
  git remote add origin https://github.com/owner/repo.git
  stub_paged_sonar
  projects_page 1 501 "$(filler_keys 499 | jq -c '["a_repo"] + .')"
  projects_page 2 501 '["z_repo"]'

  run bash "${SCRIPTS}/fetch_sonar.sh" 42
  [[ "$status" -eq 4 ]]
  [[ "$output" == *"multiple Sonar projects match 'repo'"* ]]
  [[ "$output" == *"a_repo"* ]]
  [[ "$output" == *"z_repo"* ]]
  ! grep -q '^list issues' "$SONAR_LOG"
}

@test "uses a sole project match found on a later page" {
  git remote add origin https://github.com/owner/repo.git
  stub_paged_sonar
  projects_page 1 501 "$(filler_keys 500)"
  projects_page 2 501 '["z_repo"]'
  issues_page 1 0 1 0

  run bash "${SCRIPTS}/fetch_sonar.sh" 42
  [[ "$status" -eq 0 ]]
  grep -q '^list issues --project z_repo ' "$SONAR_LOG"
}

@test "exits 5 when a later project page fails" {
  git remote add origin https://github.com/owner/repo.git
  stub_paged_sonar
  projects_page 1 501 "$(filler_keys 499 | jq -c '["a_repo"] + .')"

  run bash "${SCRIPTS}/fetch_sonar.sh" 42
  [[ "$status" -eq 5 ]]
  [[ "$output" == *"server error on page 2"* ]]
  ! grep -q '^list issues' "$SONAR_LOG"
}
