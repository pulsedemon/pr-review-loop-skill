#!/usr/bin/env bats
# tests/bats/test_fetch_pr_comments.bats — verify filter and shape contracts.
# uses a fake `gh` on PATH so tests are hermetic and don't hit the network.

load test_helper

setup() {
  TMP="$(mktemp -d)"
  FAKEBIN="$TMP/bin"
  mkdir -p "$FAKEBIN"
  cat > "$FAKEBIN/gh" <<'GHEOF'
#!/usr/bin/env bash
# minimal fake gh: routes by first two args to fixture files in $GH_FIXTURES_DIR.
# Wraps fixture output in an outer JSON array when both --paginate and --slurp
# are passed, mirroring real gh's behavior (see `gh api --help`).
wrap=0
for a in "$@"; do
  case "$a" in --slurp) wrap=1 ;; esac
done
emit() {
  if (( wrap )); then
    # jq -s wraps each top-level JSON value in the fixture into an outer array,
    # mirroring gh api --paginate --slurp. A single-array fixture becomes
    # `[[contents]]` (one page); a multi-array fixture becomes `[[p1],[p2]]`.
    jq -s '.' "$1"
  else
    cat "$1"
  fi
}
case "$1 $2" in
  "api user")
    [[ ! -f "$GH_FIXTURES_DIR/user-failure" ]] || exit 1
    cat "$GH_FIXTURES_DIR/user-login"
    ;;
  "api repos/owner/repo/pulls/1")           cat  "$GH_FIXTURES_DIR/pr.json"             ;;
  "api repos/owner/repo/issues/1/comments") emit "$GH_FIXTURES_DIR/issue_comments.json" ;;
  "api repos/owner/repo/pulls/1/comments")  emit "$GH_FIXTURES_DIR/review_comments.json";;
  "api repos/owner/repo/pulls/1/reviews")   emit "$GH_FIXTURES_DIR/reviews.json"        ;;
  "api graphql")
    cursor=""
    thread=""
    for a in "$@"; do
      case "$a" in cursor=*) cursor="${a#cursor=}" ;; thread=*) thread="${a#thread=}" ;; esac
    done
    if [[ -n "$thread" ]]; then
      cat "$GH_FIXTURES_DIR/comments-$thread-$cursor.json"
    elif [[ -n "$cursor" ]]; then
      cat "$GH_FIXTURES_DIR/threads-$cursor.json"
    elif [[ -f "$GH_FIXTURES_DIR/threads.json" ]]; then
      cat "$GH_FIXTURES_DIR/threads.json"
    else
      jq -s '
        add | group_by(.in_reply_to_id // .id) |
        map(select(any(.[]; .in_reply_to_id == null)) |
          {id: (.[0].id | tostring), isResolved: false,
           comments: {nodes: map({databaseId: .id}), pageInfo: {hasNextPage: false, endCursor: null}}}) |
        {data: {repository: {pullRequest: {reviewThreads: {nodes: ., pageInfo: {hasNextPage: false, endCursor: null}}}}}}
      ' "$GH_FIXTURES_DIR/review_comments.json"
    fi
    ;;
  *) echo "unmocked: $*" >&2; exit 99                                                   ;;
esac
GHEOF
  chmod +x "$FAKEBIN/gh"
  export PATH="$FAKEBIN:$PATH"
  export GH_FIXTURES_DIR="$TMP/fixtures"
  mkdir -p "$GH_FIXTURES_DIR"
  SCRIPT="${SCRIPTS}/fetch_pr_comments.sh"

  # baseline fixtures: PR author = "author", no comments, no threads
  echo '{"user":{"login":"author"}}' > "$GH_FIXTURES_DIR/pr.json"
  echo '[]' > "$GH_FIXTURES_DIR/issue_comments.json"
  echo '[]' > "$GH_FIXTURES_DIR/review_comments.json"
  echo '[]' > "$GH_FIXTURES_DIR/reviews.json"
  printf 'loop-author\n' > "$GH_FIXTURES_DIR/user-login"
}

teardown() {
  rm -rf "$TMP"
}

reply_artifact_fixture() {
  cat > "$GH_FIXTURES_DIR/review_comments.json" <<'JSON'
[
  {"id":10,"user":{"login":"reviewer"},"body":"root feedback","path":"a.ts","line":1,"pull_request_review_id":77,"created_at":"2026-09-21T10:00:00Z"},
  {"id":20,"user":{"login":"loop-author"},"body":"<!-- pr-review-loop-reply -->\naddressed","path":"a.ts","line":1,"pull_request_review_id":88,"in_reply_to_id":10,"created_at":"2026-09-21T10:01:00Z"}
]
JSON
  cat > "$GH_FIXTURES_DIR/reviews.json" <<'JSON'
[{"id":88,"user":{"login":"loop-author"},"body":"","state":"COMMENTED","submitted_at":"2026-09-21T10:01:00Z"}]
JSON
  cat > "$GH_FIXTURES_DIR/threads.json" <<'JSON'
{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[
  {"id":"T10","isResolved":true,"comments":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"databaseId":10},{"databaseId":20}]}}
]}}}}}
JSON
}

assert_review_is_not_reply_artifact() {
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '
    .fetch_error == null and
    (.reviews | length) == 1 and
    (.reviews[0] | has("loop_reply_artifact") | not)'
}

ordinary_reply_on_later_page_fixture() {
  reply_artifact_fixture
  cat >> "$GH_FIXTURES_DIR/review_comments.json" <<'JSON'
[
  {"id":21,"user":{"login":"loop-author"},"body":"ordinary follow-up","path":"a.ts","line":1,"pull_request_review_id":88,"in_reply_to_id":10,"created_at":"2026-09-21T10:02:00Z"}
]
JSON
  jq '.data.repository.pullRequest.reviewThreads.nodes[0].comments.nodes += [{databaseId:21}]' \
    "$GH_FIXTURES_DIR/threads.json" > "$TMP/threads-next.json"
  mv "$TMP/threads-next.json" "$GH_FIXTURES_DIR/threads.json"
}

@test "empty inputs yield four empty arrays" {
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.issue_comments==[] and .review_comments==[] and .reviews==[] and .review_threads==[]'
}

@test "drops issue comment whose first line is the loop-summary marker" {
  cat > "$GH_FIXTURES_DIR/issue_comments.json" <<'JSON'
[
  {"id":1,"user":{"login":"bot"},"body":"<!-- pr-review-loop-summary -->\n## Ready to merge","created_at":"2026-05-16T10:00:00Z"},
  {"id":2,"user":{"login":"alice"},"body":"please rename foo to bar","created_at":"2026-05-16T11:00:00Z"}
]
JSON
  run bash "$SCRIPT" owner repo 1 author
  echo "$output" | jq -e '.issue_comments | length == 1'
  echo "$output" | jq -e '.issue_comments[0].author == "alice"'
}

@test "keeps issue comment that quotes the marker mid-body" {
  cat > "$GH_FIXTURES_DIR/issue_comments.json" <<'JSON'
[{"id":3,"user":{"login":"bob"},"body":"the loop posts a comment starting with `<!-- pr-review-loop-summary -->` so be careful","created_at":"2026-05-16T12:00:00Z"}]
JSON
  run bash "$SCRIPT" owner repo 1 author
  echo "$output" | jq -e '.issue_comments | length == 1'
}

@test "drops inline review comment in a resolved thread" {
  cat > "$GH_FIXTURES_DIR/review_comments.json" <<'JSON'
[{"id":10,"user":{"login":"alice"},"body":"old nit","path":"src/x.ts","line":5,"pull_request_review_id":99,"created_at":"2026-05-16T09:00:00Z"}]
JSON
  cat > "$GH_FIXTURES_DIR/threads.json" <<'JSON'
{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[
  {"id":"T1","isResolved":true,"comments":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"id":"C1","databaseId":10}]}}
]}}}}}
JSON
  run bash "$SCRIPT" owner repo 1 author
  echo "$output" | jq -e '.review_comments | length == 0'
}

@test "tags pr-author comment with is_pr_author true" {
  cat > "$GH_FIXTURES_DIR/issue_comments.json" <<'JSON'
[{"id":1,"user":{"login":"author"},"body":"intent: this is on purpose","created_at":"2026-05-16T10:00:00Z"}]
JSON
  run bash "$SCRIPT" owner repo 1 author
  echo "$output" | jq -e '.issue_comments[0].is_pr_author == true'
}

@test "orders issue_comments by created_at ascending" {
  cat > "$GH_FIXTURES_DIR/issue_comments.json" <<'JSON'
[
  {"id":2,"user":{"login":"alice"},"body":"second","created_at":"2026-05-16T12:00:00Z"},
  {"id":1,"user":{"login":"bob"},"body":"first","created_at":"2026-05-16T10:00:00Z"}
]
JSON
  run bash "$SCRIPT" owner repo 1 author
  echo "$output" | jq -e '.issue_comments[0].body == "first" and .issue_comments[1].body == "second"'
}

@test "keeps all review records regardless of state" {
  cat > "$GH_FIXTURES_DIR/reviews.json" <<'JSON'
[
  {"id":1,"user":{"login":"alice"},"body":"","state":"APPROVED","submitted_at":"2026-05-16T10:00:00Z"},
  {"id":2,"user":{"login":"bob"},"body":"please fix the lock","state":"CHANGES_REQUESTED","submitted_at":"2026-05-16T11:00:00Z"}
]
JSON
  run bash "$SCRIPT" owner repo 1 author
  echo "$output" | jq -e '.reviews | length == 2'
}

@test "success path emits fetched_at and fetch_error: null" {
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == null'
  echo "$output" | jq -e '.fetched_at | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")'
}

@test "paginated fixtures across all three REST endpoints flatten correctly" {
  # multi-page fixture: each top-level JSON array represents one page of results,
  # mirroring what `gh api --paginate --slurp` collapses into `[[p1],[p2]]`.
  cat > "$GH_FIXTURES_DIR/issue_comments.json" <<'JSON'
[
  {"id":1,"user":{"login":"alice"},"body":"page1 first","created_at":"2026-05-16T10:00:00Z"},
  {"id":2,"user":{"login":"alice"},"body":"page1 second","created_at":"2026-05-16T10:01:00Z"}
]
[
  {"id":3,"user":{"login":"bob"},"body":"page2 first","created_at":"2026-05-16T11:00:00Z"}
]
JSON
  cat > "$GH_FIXTURES_DIR/review_comments.json" <<'JSON'
[
  {"id":10,"user":{"login":"alice"},"body":"rc1","path":"a.ts","line":1,"pull_request_review_id":99,"created_at":"2026-05-16T09:00:00Z"}
]
[
  {"id":11,"user":{"login":"bob"},"body":"rc2","path":"b.ts","line":2,"pull_request_review_id":99,"created_at":"2026-05-16T09:30:00Z"}
]
JSON
  cat > "$GH_FIXTURES_DIR/reviews.json" <<'JSON'
[
  {"id":1,"user":{"login":"alice"},"body":"r1","state":"APPROVED","submitted_at":"2026-05-16T10:00:00Z"}
]
[
  {"id":2,"user":{"login":"bob"},"body":"r2","state":"COMMENTED","submitted_at":"2026-05-16T10:30:00Z"}
]
JSON
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.issue_comments  | length == 3'
  echo "$output" | jq -e '.review_comments | length == 2'
  echo "$output" | jq -e '.reviews         | length == 2'
  # ordering still holds across pages
  echo "$output" | jq -e '.issue_comments[0].body == "page1 first" and .issue_comments[2].body == "page2 first"'
}

@test "gh API failure path emits empty arrays plus fetch_error message" {
  # override fake gh to fail on the issue_comments fetch
  cat > "$FAKEBIN/gh" <<'GHEOF'
#!/usr/bin/env bash
case "$1 $2" in
  "api repos/owner/repo/pulls/1") cat "$GH_FIXTURES_DIR/pr.json" ;;
  "api repos/owner/repo/issues/1/comments") exit 1 ;;
  *) echo "unmocked: $*" >&2; exit 99 ;;
esac
GHEOF
  chmod +x "$FAKEBIN/gh"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.issue_comments==[] and .review_comments==[] and .reviews==[] and .review_threads==[]'
  echo "$output" | jq -e '.fetch_error == "issue_comments fetch failed"'
  echo "$output" | jq -e '.fetched_at | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")'
}

@test "GraphQL errors envelope is treated as a fetch failure (does not silently empty RESOLVED_MAP)" {
  # threads.json simulates `gh api graphql` returning exit 0 with an `errors`
  # body (rate-limit / auth-scope failure). Without the explicit `has("errors")`
  # check the THREADS jq parse would null-coalesce to []. and any inline review
  # comment whose thread was resolved would leak past the filter.
  echo '{"errors":[{"message":"rate limited"}]}' > "$GH_FIXTURES_DIR/threads.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "review_threads graphql errors"'
  echo "$output" | jq -e '.issue_comments==[] and .review_comments==[] and .reviews==[] and .review_threads==[]'
}

@test "GraphQL FORBIDDEN errors envelope (auth scope) is treated as a fetch failure" {
  # distinct from rate-limit by error type — exercises the same has("errors") path.
  echo '{"errors":[{"type":"FORBIDDEN","message":"resource not accessible"}]}' > "$GH_FIXTURES_DIR/threads.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "review_threads graphql errors"'
}

@test "gh stderr is included in fetch_error for triage" {
  cat > "$FAKEBIN/gh" <<'GHEOF'
#!/usr/bin/env bash
case "$1 $2" in
  "api repos/owner/repo/issues/1/comments") echo "HTTP 401: Bad credentials" >&2; exit 1 ;;
  *) echo "unmocked: $*" >&2; exit 99 ;;
esac
GHEOF
  chmod +x "$FAKEBIN/gh"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error | test("issue_comments fetch failed: HTTP 401")'
}

@test "missing gh binary exits 7" {
  # drop the fake gh stub and narrow PATH to FAKEBIN only. CI runners ship a
  # real gh in /usr/bin, so including it here would let `command -v gh` succeed
  # and mask the missing-binary path. invoke bash via an absolute path because
  # bats's `run` needs to locate the binary itself before the narrowed PATH
  # takes effect inside the script. the script exits 7 before needing any
  # other tool, so an otherwise-empty PATH is fine.
  rm "$FAKEBIN/gh"
  PATH="$FAKEBIN" run /bin/bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 7 ]
}

@test "missing pr_author surfaces fetch_error: pr_author_missing" {
  run bash "$SCRIPT" owner repo 1
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "pr_author_missing"'
  echo "$output" | jq -e '.issue_comments==[] and .review_comments==[] and .reviews==[] and .review_threads==[]'
}

@test "review_comments output carries review_id (not thread_id)" {
  cat > "$GH_FIXTURES_DIR/review_comments.json" <<'JSON'
[{"id":42,"user":{"login":"alice"},"body":"x","path":"a.ts","line":3,"pull_request_review_id":777,"created_at":"2026-05-16T10:00:00Z"}]
JSON
  run bash "$SCRIPT" owner repo 1 author
  echo "$output" | jq -e '.review_comments[0].review_id == "777"'
  echo "$output" | jq -e '.review_comments[0] | has("thread_id") | not'
}

@test "review_comments classify thread roots vs replies via in_reply_to_id" {
  cat > "$GH_FIXTURES_DIR/review_comments.json" <<'JSON'
[
  {"id":30,"user":{"login":"alice"},"body":"root comment","path":"a.ts","line":3,"pull_request_review_id":99,"created_at":"2026-05-16T10:00:00Z"},
  {"id":31,"user":{"login":"bob"},"body":"human reply","path":"a.ts","line":3,"pull_request_review_id":99,"in_reply_to_id":30,"created_at":"2026-05-16T10:05:00Z"}
]
JSON
  run bash "$SCRIPT" owner repo 1 author
  echo "$output" | jq -e '.review_comments[] | select(.id == "30") | (.is_thread_root == true) and (.in_reply_to_id == null)'
  echo "$output" | jq -e '.review_comments[] | select(.id == "31") | (.is_thread_root == false) and (.in_reply_to_id == "30")'
}

@test "resolved thread with multiple comments filters all of them" {
  cat > "$GH_FIXTURES_DIR/review_comments.json" <<'JSON'
[
  {"id":10,"user":{"login":"alice"},"body":"a","path":"x.ts","line":1,"pull_request_review_id":99,"created_at":"2026-05-16T09:00:00Z"},
  {"id":11,"user":{"login":"alice"},"body":"b","path":"x.ts","line":2,"pull_request_review_id":99,"in_reply_to_id":10,"created_at":"2026-05-16T09:01:00Z"}
]
JSON
  cat > "$GH_FIXTURES_DIR/threads.json" <<'JSON'
{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[
  {"id":"T1","isResolved":true,"comments":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"id":"C1","databaseId":10},{"id":"C2","databaseId":11}]}}
]}}}}}
JSON
  run bash "$SCRIPT" owner repo 1 author
  echo "$output" | jq -e '.review_comments | length == 0'
}

@test "drops issue comment whose first line is the loop-reply marker" {
  cat > "$GH_FIXTURES_DIR/issue_comments.json" <<'JSON'
[
  {"id":1,"user":{"login":"bot"},"body":"<!-- pr-review-loop-reply -->\nNot changed in this review — out of scope","created_at":"2026-05-16T10:00:00Z"},
  {"id":2,"user":{"login":"alice"},"body":"please rename foo to bar","created_at":"2026-05-16T11:00:00Z"}
]
JSON
  run bash "$SCRIPT" owner repo 1 author
  echo "$output" | jq -e '.issue_comments | length == 1'
  echo "$output" | jq -e '.issue_comments[0].author == "alice"'
}

@test "drops inline review comment whose first line is the loop-reply marker" {
  cat > "$GH_FIXTURES_DIR/review_comments.json" <<'JSON'
[
  {"id":10,"user":{"login":"alice"},"body":"root","path":"a.ts","line":4,"pull_request_review_id":99,"created_at":"2026-05-16T09:20:00Z"},
  {"id":20,"user":{"login":"bot"},"body":"<!-- pr-review-loop-reply -->\nUpdated in abc123","path":"a.ts","line":4,"pull_request_review_id":99,"in_reply_to_id":10,"created_at":"2026-05-16T09:30:00Z"},
  {"id":21,"user":{"login":"alice"},"body":"real nit","path":"a.ts","line":4,"pull_request_review_id":99,"created_at":"2026-05-16T09:40:00Z"}
]
JSON
  run bash "$SCRIPT" owner repo 1 author
  echo "$output" | jq -e '[.review_comments[].id] == ["10", "21"]'
}

@test "retains and annotates an empty COMMENTED review created by an owned marker reply" {
  reply_artifact_fixture
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '
    .fetch_error == null and
    .review_comments == [] and
    .reviews == [{id:"88",author:"loop-author",is_pr_author:false,body:"",state:"COMMENTED",
      submitted_at:"2026-09-21T10:01:00Z",source:"review",loop_reply_artifact:true}] and
    (.review_threads | length) == 1 and
    .review_threads[0].root_comment_id == "10" and
    .review_threads[0].has_reply == true and
    .review_threads[0].replies == []'
}

@test "identity lookup failure retains the empty COMMENTED review without annotation" {
  reply_artifact_fixture
  touch "$GH_FIXTURES_DIR/user-failure"
  assert_review_is_not_reply_artifact
}

@test "empty authenticated identity retains the empty COMMENTED review without annotation" {
  reply_artifact_fixture
  : > "$GH_FIXTURES_DIR/user-login"
  assert_review_is_not_reply_artifact
}

@test "a whitespace review body is not annotated as a reply artifact" {
  reply_artifact_fixture
  jq '.[0].body = " "' "$GH_FIXTURES_DIR/reviews.json" > "$TMP/reviews-next.json"
  mv "$TMP/reviews-next.json" "$GH_FIXTURES_DIR/reviews.json"
  assert_review_is_not_reply_artifact
}

@test "a substantive review body is not annotated as a reply artifact" {
  reply_artifact_fixture
  jq '.[0].body = "review objection"' "$GH_FIXTURES_DIR/reviews.json" > "$TMP/reviews-next.json"
  mv "$TMP/reviews-next.json" "$GH_FIXTURES_DIR/reviews.json"
  assert_review_is_not_reply_artifact
}

@test "an APPROVED review is not annotated as a reply artifact" {
  reply_artifact_fixture
  jq '.[0].state = "APPROVED"' "$GH_FIXTURES_DIR/reviews.json" > "$TMP/reviews-next.json"
  mv "$TMP/reviews-next.json" "$GH_FIXTURES_DIR/reviews.json"
  assert_review_is_not_reply_artifact
}

@test "a CHANGES_REQUESTED review is not annotated as a reply artifact" {
  reply_artifact_fixture
  jq '.[0].state = "CHANGES_REQUESTED"' "$GH_FIXTURES_DIR/reviews.json" > "$TMP/reviews-next.json"
  mv "$TMP/reviews-next.json" "$GH_FIXTURES_DIR/reviews.json"
  assert_review_is_not_reply_artifact
}

@test "a DISMISSED review is not annotated as a reply artifact" {
  reply_artifact_fixture
  jq '.[0].state = "DISMISSED"' "$GH_FIXTURES_DIR/reviews.json" > "$TMP/reviews-next.json"
  mv "$TMP/reviews-next.json" "$GH_FIXTURES_DIR/reviews.json"
  assert_review_is_not_reply_artifact
}

@test "a foreign review author is not annotated as a reply artifact" {
  reply_artifact_fixture
  jq '.[0].user.login = "someone-else"' "$GH_FIXTURES_DIR/reviews.json" > "$TMP/reviews-next.json"
  mv "$TMP/reviews-next.json" "$GH_FIXTURES_DIR/reviews.json"
  assert_review_is_not_reply_artifact
}

@test "a foreign marker reply author is not annotated as a reply artifact" {
  reply_artifact_fixture
  jq 'map(if .id == 20 then .user.login = "someone-else" else . end)' \
    "$GH_FIXTURES_DIR/review_comments.json" > "$TMP/comments-next.json"
  mv "$TMP/comments-next.json" "$GH_FIXTURES_DIR/review_comments.json"
  assert_review_is_not_reply_artifact
}

@test "an unlinked marker reply review is not annotated as a reply artifact" {
  reply_artifact_fixture
  jq 'map(if .id == 20 then .pull_request_review_id = 89 else . end)' \
    "$GH_FIXTURES_DIR/review_comments.json" > "$TMP/comments-next.json"
  mv "$TMP/comments-next.json" "$GH_FIXTURES_DIR/review_comments.json"
  assert_review_is_not_reply_artifact
}

@test "a review containing the thread root is not annotated as a reply artifact" {
  reply_artifact_fixture
  jq 'map(if .id == 10 then
    .pull_request_review_id = 88 |
    .user.login = "loop-author" |
    .body = "<!-- pr-review-loop-reply -->\nroot marker"
    else . end)' \
    "$GH_FIXTURES_DIR/review_comments.json" > "$TMP/comments-next.json"
  mv "$TMP/comments-next.json" "$GH_FIXTURES_DIR/review_comments.json"
  assert_review_is_not_reply_artifact
}

@test "a later-page ordinary same-user reply remains in the resolved thread before filtering" {
  ordinary_reply_on_later_page_fixture
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '
    .fetch_error == null and
    (.reviews[0] | has("loop_reply_artifact") | not) and
    .review_comments == [] and
    .review_threads[0].has_reply == true and
    [.review_threads[0].replies[].id] == ["21"] and
    .review_threads[0].replies[0].body == "ordinary follow-up"'
}

@test "a later-page ordinary same-user reply remains in both unresolved comment views" {
  ordinary_reply_on_later_page_fixture
  jq '.data.repository.pullRequest.reviewThreads.nodes[0].isResolved = false' \
    "$GH_FIXTURES_DIR/threads.json" > "$TMP/threads-next.json"
  mv "$TMP/threads-next.json" "$GH_FIXTURES_DIR/threads.json"

  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '
    .fetch_error == null and
    (.reviews[0] | has("loop_reply_artifact") | not) and
    [.review_comments[].id] == ["10", "21"] and
    [.review_threads[0].replies[].id] == ["21"] and
    .review_threads[0].replies[0].body == "ordinary follow-up"'
}

paginated_threads() {
  cat > "$GH_FIXTURES_DIR/review_comments.json" <<'JSON'
[
  {"id":10,"user":{"login":"alice"},"body":"root","path":"a.ts","line":3,"pull_request_review_id":99,"created_at":"2026-05-16T10:00:00Z"},
  {"id":11,"user":{"login":"author"},"body":"<!-- pr-review-loop-reply -->\nfixed","path":"a.ts","line":3,"pull_request_review_id":99,"in_reply_to_id":10,"created_at":"2026-05-16T10:05:00Z"},
  {"id":20,"user":{"login":"copilot[bot]"},"body":"unanswered","path":"b.ts","line":4,"pull_request_review_id":100,"created_at":"2026-05-16T11:00:00Z"}
]
JSON
  cat > "$GH_FIXTURES_DIR/threads.json" <<'JSON'
{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":true,"endCursor":"T1"},"nodes":[
  {"id":"T1","isResolved":true,"comments":{"pageInfo":{"hasNextPage":true,"endCursor":"C1"},"nodes":[{"databaseId":10}]}}
]}}}}}
JSON
  cat > "$GH_FIXTURES_DIR/comments-T1-C1.json" <<'JSON'
{"data":{"node":{"comments":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"databaseId":11}]}}}}
JSON
  cat > "$GH_FIXTURES_DIR/threads-T1.json" <<'JSON'
{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[
  {"id":"T2","isResolved":true,"comments":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"databaseId":20}]}}
]}}}}}
JSON
}

@test "paginates threads and comments while retaining resolved unanswered bot roots" {
  paginated_threads
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '
    .fetch_error == null and .review_comments == [] and
    (.review_threads | length == 2) and
    .review_threads[0].comment_ids == ["10", "11"] and
    .review_threads[0].has_reply == true and
    .review_threads[1].has_reply == false and
    .review_threads[1].is_resolved == true and
    .review_threads[1].root_comment_id == "20" and
    .review_threads[1].root_comment.author == "copilot[bot]" and
    .review_threads[1].root_comment.body == "unanswered"'
}

@test "a later thread page failure discards partial results" {
  paginated_threads
  echo '{"errors":[{"message":"rate limited"}]}' > "$GH_FIXTURES_DIR/threads-T1.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error != null and .review_threads == [] and .review_comments == []'
}

@test "a later comment page failure discards partial results" {
  paginated_threads
  rm "$GH_FIXTURES_DIR/comments-T1-C1.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error != null and .review_threads == []'
}

@test "missing GraphQL response data and pagination fields are incomplete" {
  for fixture in \
    '{"data":"unavailable"}' \
    '{"data":{"repository":{"pullRequest":null}}}' \
    '{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[]}}}}}' \
    '{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[],"pageInfo":{"hasNextPage":true,"endCursor":null}}}}}}'; do
    printf '%s' "$fixture" > "$GH_FIXTURES_DIR/threads.json"
    run bash "$SCRIPT" owner repo 1 author
    [ "$status" -eq 0 ]
    echo "$output" | jq -e '.fetch_error == "review_threads incomplete data"'
  done
}

@test "missing nested comment pagination data is incomplete" {
  paginated_threads
  echo '{"data":{"node":{"comments":{"nodes":[]}}}}' > "$GH_FIXTURES_DIR/comments-T1-C1.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "review_threads incomplete comments"'
}

@test "a repeated thread cursor cannot silently truncate discovery" {
  paginated_threads
  cp "$GH_FIXTURES_DIR/threads.json" "$GH_FIXTURES_DIR/threads-T1.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "review_threads repeated thread cursor"'
}

@test "a repeated comment cursor cannot silently truncate discovery" {
  paginated_threads
  echo '{"data":{"node":{"comments":{"pageInfo":{"hasNextPage":true,"endCursor":"C1"},"nodes":[{"databaseId":11}]}}}}' > "$GH_FIXTURES_DIR/comments-T1-C1.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "review_threads repeated comment cursor"'
}

@test "a thread root missing from REST comments prevents success" {
  paginated_threads
  echo '[]' > "$GH_FIXTURES_DIR/review_comments.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "review_threads missing REST comment content"'
}

@test "a malformed REST page prevents success" {
  echo '{"message":"partial response"}' > "$GH_FIXTURES_DIR/issue_comments.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "comments incomplete REST data"'
}

@test "a REST root absent from GraphQL prevents success" {
  paginated_threads
  echo '{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[]}}}}}' > "$GH_FIXTURES_DIR/threads.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "review_threads missing REST comment or root"'
}

@test "first page runs with the system bash empty-array semantics" {
  run /bin/bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == null'
}

@test "thread output excludes loop marker roots and retains ordinary bot roots" {
  cat > "$GH_FIXTURES_DIR/review_comments.json" <<'JSON'
[
  {"id":40,"user":{"login":"author"},"body":"<!-- pr-review-loop-reply -->\nfixed","path":"a.ts","line":1,"pull_request_review_id":99,"created_at":"2026-05-16T10:00:00Z"},
  {"id":41,"user":{"login":"copilot[bot]"},"body":"please fix","path":"a.ts","line":1,"pull_request_review_id":99,"created_at":"2026-05-16T10:00:00Z"},
  {"id":42,"user":{"login":"author"},"body":"<!-- pr-review-loop-summary -->\nready","path":"a.ts","line":1,"pull_request_review_id":99,"created_at":"2026-05-16T10:00:00Z"}
]
JSON
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == null and [.review_threads[].root_comment_id] == ["41"] and [.review_comments[].id] == ["41"]'
}


@test "a REST reply without its GraphQL root prevents success" {
  echo '[{"id":11,"body":"reply","user":{"login":"bot"},"in_reply_to_id":10}]' > "$GH_FIXTURES_DIR/review_comments.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "review_threads missing REST comment or root"'
}

@test "a reply missing from a discovered GraphQL thread prevents success" {
  paginated_threads
  echo '{"data":{"node":{"comments":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[]}}}}' > "$GH_FIXTURES_DIR/comments-T1-C1.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "review_threads missing REST comment or root"'
}

@test "a GraphQL reply missing from REST comment content prevents success" {
  paginated_threads
  jq 'map(select(.id != 11))' "$GH_FIXTURES_DIR/review_comments.json" > "$TMP/edited.json"
  mv "$TMP/edited.json" "$GH_FIXTURES_DIR/review_comments.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "review_threads missing REST comment content"'
  echo "$output" | jq -e '.review_threads == [] and .review_comments == []'
}

@test "a GraphQL first comment that is a REST reply cannot become a root" {
  paginated_threads
  jq 'map(if .id == 10 then .in_reply_to_id = 9 else . end)' "$GH_FIXTURES_DIR/review_comments.json" > "$TMP/edited.json"
  mv "$TMP/edited.json" "$GH_FIXTURES_DIR/review_comments.json"
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.fetch_error == "review_threads missing root comment"'
}

@test "normalization failures retain the fetch error envelope" {
  bats_require_minimum_version 1.5.0
  for endpoint in issue_comments review_comments reviews; do
    echo '[{"id":10,"body":"comment","user":[]}]' > "$GH_FIXTURES_DIR/$endpoint.json"
    run --separate-stderr bash "$SCRIPT" owner repo 1 author
    [ "$status" -eq 0 ]
    echo "$output" | jq -e '.fetch_error == "comments normalization failed" and .review_threads == []'
    echo '[]' > "$GH_FIXTURES_DIR/$endpoint.json"
  done
}

@test "resolved threads retain normalized external replies and exclude owned markers" {
  local decision edited followup initial state
  initial="$TMP/initial.json"
  followup="$TMP/followup.json"
  edited="$TMP/edited.json"
  state="$TMP/comment-state.json"
  decision="$TMP/comment-decision.json"
  cat > "$GH_FIXTURES_DIR/review_comments.json" <<'JSON'
[
  {"id":100,"user":{"login":"review-bot[bot]","type":"Bot"},"body":"root feedback","path":"src/a.py","line":7,"pull_request_review_id":90,"created_at":"2026-09-18T10:00:00Z"},
  {"id":101,"user":{"login":"author","type":"User"},"body":"<!-- pr-review-loop-reply -->\naddressed","path":"src/a.py","line":7,"pull_request_review_id":90,"in_reply_to_id":100,"created_at":"2026-09-18T10:01:00Z"},
  {"id":200,"user":{"login":"review-model","type":"User"},"body":"model-style feedback from a human account","path":"src/b.py","line":9,"pull_request_review_id":91,"created_at":"2026-09-18T11:00:00Z"},
  {"id":201,"user":{"login":"author","type":"User"},"body":"<!-- pr-review-loop-reply -->\nhandled","path":"src/b.py","line":9,"pull_request_review_id":91,"in_reply_to_id":200,"created_at":"2026-09-18T11:01:00Z"}
]
JSON
  cat > "$GH_FIXTURES_DIR/threads.json" <<'JSON'
{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[
  {"id":"T100","isResolved":true,"comments":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"databaseId":100},{"databaseId":101}]}},
  {"id":"T200","isResolved":true,"comments":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"databaseId":200},{"databaseId":201}]}}
]}}}}}
JSON
  bash "$SCRIPT" owner repo 1 author > "$initial"
  jq '. += [{id:102,user:{login:"review-bot[bot]",type:"Bot"},
    body:"first follow-up from the model",path:"src/a.py",line:7,
    pull_request_review_id:90,in_reply_to_id:100,created_at:"2026-09-18T10:02:00Z"}]' \
    "$GH_FIXTURES_DIR/review_comments.json" > "$TMP/comments-next.json"
  mv "$TMP/comments-next.json" "$GH_FIXTURES_DIR/review_comments.json"
  jq '.data.repository.pullRequest.reviewThreads.nodes[0].comments.nodes += [{databaseId:102}]' \
    "$GH_FIXTURES_DIR/threads.json" > "$TMP/threads-next.json"
  mv "$TMP/threads-next.json" "$GH_FIXTURES_DIR/threads.json"
  bash "$SCRIPT" owner repo 1 author > "$followup"
  jq -e '
    .fetch_error == null and
    .review_comments == [] and
    .review_threads[0].is_resolved == true and
    .review_threads[0].has_reply == true and
    .review_threads[0].root_comment.body == "root feedback" and
    [.review_threads[0].replies[].id] == ["102"] and
    .review_threads[0].replies[0].body == "first follow-up from the model" and
    .review_threads[1].root_comment.author == "review-model" and
    .review_threads[1].root_comment.body == "model-style feedback from a human account" and
    .review_threads[1].has_reply == true and
    ([.review_threads[].replies[].body] | all(startswith("<!-- pr-review-loop-reply -->") | not))' \
    "$followup"

  jq -n --slurpfile comments "$initial" '{
    iteration:1,max_iterations:15,status:"running",
    history:[{human_comments:$comments[0]}],
    comment_ledger:[{id:"100",source:"review_comment",disposition:"addressed",
      replied_at:"2026-09-18T10:05:00Z"}]
  }' > "$state"
  jq -n --slurpfile comments "$followup" '{phase:"comments",comments:$comments[0]}' |
    python3 "$SCRIPTS/check_exit_conditions.py" --state "$state" > "$decision"
  jq -e '.continue_full_panel == true and .disposition_root_ids == ["100"]' "$decision"

  jq --slurpfile comments "$followup" '.history[0].human_comments = $comments[0]' \
    "$state" > "$TMP/state-next.json"
  mv "$TMP/state-next.json" "$state"
  jq 'map(if .id == 102 then .body = "edited follow-up from the model" else . end)' \
    "$GH_FIXTURES_DIR/review_comments.json" > "$TMP/comments-next.json"
  mv "$TMP/comments-next.json" "$GH_FIXTURES_DIR/review_comments.json"
  bash "$SCRIPT" owner repo 1 author > "$edited"
  jq -e '
    .review_comments == [] and
    .review_threads[0].replies[0].body == "edited follow-up from the model"' "$edited"
  jq -n --slurpfile comments "$edited" '{phase:"comments",comments:$comments[0]}' |
    python3 "$SCRIPTS/check_exit_conditions.py" --state "$state" > "$decision"
  jq -e '.continue_full_panel == true and .disposition_root_ids == ["100"]' "$decision"
}

@test "unresolved handled threads expose bot follow-ups in both comment views" {
  cat > "$GH_FIXTURES_DIR/review_comments.json" <<'JSON'
[
  {"id":300,"user":{"login":"review-bot[bot]","type":"Bot"},"body":"root feedback","path":"src/c.py","line":12,"pull_request_review_id":92,"created_at":"2026-09-18T12:00:00Z"},
  {"id":301,"user":{"login":"author","type":"User"},"body":"<!-- pr-review-loop-reply -->\nhandled","path":"src/c.py","line":12,"pull_request_review_id":92,"in_reply_to_id":300,"created_at":"2026-09-18T12:01:00Z"},
  {"id":302,"user":{"login":"review-bot[bot]","type":"Bot"},"body":"external follow-up","path":"src/c.py","line":12,"pull_request_review_id":92,"in_reply_to_id":300,"created_at":"2026-09-18T12:02:00Z"}
]
JSON
  cat > "$GH_FIXTURES_DIR/threads.json" <<'JSON'
{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[
  {"id":"T300","isResolved":false,"comments":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"databaseId":300},{"databaseId":301},{"databaseId":302}]}}
]}}}}}
JSON
  run bash "$SCRIPT" owner repo 1 author
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '
    .fetch_error == null and
    [.review_comments[].id] == ["300", "302"] and
    [.review_threads[0].replies[].id] == ["302"] and
    .review_comments[1].body == "external follow-up" and
    .review_threads[0].replies[0].body == "external follow-up" and
    .review_threads[0].has_reply == true and
    ([.review_comments[].body, .review_threads[].replies[].body] | flatten |
      all(startswith("<!-- pr-review-loop-reply -->") | not))'
}

@test "large paginated comment envelopes survive fetch decision and state persistence" {
  local fetched initial_decision append_packet unchanged_decision state
  fetched="$TMP/fetched.json"
  initial_decision="$TMP/initial-decision.json"
  append_packet="$TMP/append-packet.json"
  unchanged_decision="$TMP/unchanged-decision.json"
  state="$TMP/state.json"

  jq -n '
    def padded($prefix; $fill): $prefix + ($fill * (8192 - ($prefix | length)));
    [range(0; 247) as $i |
      {id: (100000 + $i), user: {login: "review-bot[bot]", type: "Bot"},
       body: padded("root-\($i):"; "r"), path: "src/large.py", line: ($i + 1),
       pull_request_review_id: (600000 + $i), created_at: "2026-09-18T10:00:00Z"},
      (if $i == 0 then
        {id: 19999, user: {login: "author", type: "User"},
         body: "<!-- pr-review-loop-reply -->\nhandled", path: "src/large.py", line: 1,
         pull_request_review_id: 600000, in_reply_to_id: 100000,
         created_at: "2026-09-18T10:01:00Z"}
       else empty end),
      {id: (200000 + $i), user: {login: "review-bot[bot]", type: "Bot"},
       body: padded("bot-reply-\($i):"; "b"), path: "src/large.py", line: ($i + 1),
       pull_request_review_id: (600000 + $i), in_reply_to_id: (100000 + $i),
       created_at: "2026-09-18T10:02:00Z"}]
  ' > "$GH_FIXTURES_DIR/review_comments.json"
  jq -n '
    def padded($prefix): $prefix + ("i" * (8192 - ($prefix | length)));
    [range(0; 160) as $i |
      {id: (400000 + $i), user: {login: "issue-user"}, body: padded("issue-\($i):"),
       created_at: "2026-09-18T09:00:00Z"}]' > "$GH_FIXTURES_DIR/issue_comments.json"
  jq -n '
    def padded($prefix): $prefix + ("v" * (8192 - ($prefix | length)));
    [range(0; 160) as $i |
      {id: (500000 + $i), user: {login: "review-user"}, body: padded("review-\($i):"),
       state: "COMMENTED", submitted_at: "2026-09-18T09:30:00Z"}]' > "$GH_FIXTURES_DIR/reviews.json"

  write_thread_page() {
    local start="$1" stop="$2" next="$3" destination="$4"
    jq -n --argjson start "$start" --argjson stop "$stop" --arg next "$next" '
      {data: {repository: {pullRequest: {reviewThreads: {
        pageInfo: {hasNextPage: ($next != ""), endCursor: (if $next == "" then null else $next end)},
        nodes: [range($start; $stop) as $i |
          {id: "T-\($i)", isResolved: true,
           comments: {pageInfo: {hasNextPage: false, endCursor: null},
             nodes: ([{databaseId: (100000 + $i)}] +
               (if $i == 0 then [{databaseId: 19999}] else [] end) +
               [{databaseId: (200000 + $i)}])}}]
      }}}}}' > "$destination"
  }
  write_thread_page 0 100 page-2 "$GH_FIXTURES_DIR/threads.json"
  write_thread_page 100 200 page-3 "$GH_FIXTURES_DIR/threads-page-2.json"
  write_thread_page 200 247 '' "$GH_FIXTURES_DIR/threads-page-3.json"

  bash "$SCRIPT" owner repo 1 author > "$fetched"
  jq -e \
    --slurpfile rest "$GH_FIXTURES_DIR/review_comments.json" \
    --slurpfile issues "$GH_FIXTURES_DIR/issue_comments.json" \
    --slurpfile reviews "$GH_FIXTURES_DIR/reviews.json" '
    .fetch_error == null and .review_comments == [] and
    (.issue_comments | length) == 160 and (.reviews | length) == 160 and
    (.review_threads | length) == 247 and
    ([.review_threads[].replies[]] | length) == 247 and
    ([.issue_comments[] | {id,body}] ==
      [$issues[0][] | {id:(.id | tostring),body}]) and
    ([.reviews[] | {id,body}] ==
      [$reviews[0][] | {id:(.id | tostring),body}]) and
    ([.review_threads[].root_comment | {id,body}] ==
      [$rest[0][] | select(.in_reply_to_id == null) | {id:(.id | tostring),body}]) and
    ([.review_threads[].replies[] | {id,body}] ==
      [$rest[0][] | select(.in_reply_to_id != null) |
        select((.body | startswith("<!-- pr-review-loop-reply -->")) | not) |
        {id:(.id | tostring),body}]) and
    (all(.issue_comments[]; (.body | length) == 8192)) and
    (all(.reviews[]; (.body | length) == 8192)) and
    (all(.review_threads[]; .has_reply and (.root_comment.body | length) == 8192 and
      (.replies | length) == 1 and (.replies[0].body | length) == 8192)) and
    .review_threads[0].root_comment_id == "100000" and
    .review_threads[246].root_comment_id == "100246" and
    .review_threads[0].replies[0].id == "200000" and
    .review_threads[246].replies[0].id == "200246" and
    .review_threads[0].root_comment.body == ($rest[0][] | select(.id == 100000) | .body) and
    .review_threads[0].replies[0].body == ($rest[0][] | select(.id == 200000) | .body) and
    .review_threads[246].root_comment.body == ($rest[0][] | select(.id == 100246) | .body) and
    .review_threads[246].replies[0].body == ($rest[0][] | select(.id == 200246) | .body) and
    ([.review_threads[].replies[].body] |
      all(startswith("<!-- pr-review-loop-reply -->") | not))' "$fetched"

  cat > "$state" <<'JSON'
{"iteration":0,"max_iterations":15,"status":"running","history":[],"approvers_required_list":["tests"]}
JSON
  jq -n --slurpfile comments "$fetched" \
    '{phase:"comments",comments:$comments[0]}' |
    python3 "$SCRIPTS/check_exit_conditions.py" --state "$state" > "$initial_decision"
  jq -e '.terminal_status == null and .continue_full_panel == true and .disposition_root_ids == []' \
    "$initial_decision"

  jq -n --slurpfile comments "$fetched" '{
    entry: {
      head_sha_before: "large-head", head_sha_after: "large-head", findings: [],
      ci_status: "skipped", human_comments: $comments[0], reviewers_completed: ["tests"],
      panel_selection: {mode:"full",ran:["tests"],skipped:[],gate_relevant:[],
        gate_fail_open:[],open_blocker_carryover:[]}
    },
    comment_updates: []
  }' > "$append_packet"
  python3 "$SCRIPTS/pr_loop_state.py" append-history --state "$state" --input-json - \
    < "$append_packet" > /dev/null
  jq -e --slurpfile comments "$fetched" \
    '.iteration == 1 and .history[0].human_comments == $comments[0]' "$state"

  jq -n --slurpfile comments "$fetched" \
    '{phase:"comments",comments:$comments[0]}' |
    python3 "$SCRIPTS/check_exit_conditions.py" --state "$state" > "$unchanged_decision"
  jq -e '.terminal_status == null and .continue_full_panel == false and .disposition_root_ids == []' \
    "$unchanged_decision"
}
