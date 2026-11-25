#!/usr/bin/env bats
# tests/bats/test_reply_pr_comments.bats: idempotent, marker-tagged reply poster.
# hermetic fake gh on PATH; persists remote comments and records mutations.

load test_helper

setup() {
  TMP="$(mktemp -d)"
  FAKEBIN="$TMP/bin"
  mkdir -p "$FAKEBIN"
  export REMOTE_COMMENTS="$TMP/remote-comments.json"
  export REMOTE_REVIEWS="$TMP/remote-reviews.json"
  export CURRENT_USER_FILE="$TMP/current-user"
  export MUTATION_LOG="$TMP/mutations.jsonl"
  export AUTH_FAIL="$TMP/auth-fail"
  export SCAN_FAIL="$TMP/scan-fail"
  export POST_FAIL="$TMP/post-fail"
  export PATCH_FAIL="$TMP/patch-fail"
  printf 'loop-author\n' > "$CURRENT_USER_FILE"
  : > "$MUTATION_LOG"
  cat > "$REMOTE_COMMENTS" <<'JSON'
[[{"id":10,"user":{"login":"reviewer"},"body":"root feedback","path":"a.ts","line":1,"pull_request_review_id":77,"created_at":"2026-09-21T10:00:00Z"}]]
JSON
  echo '[[]]' > "$REMOTE_REVIEWS"
  cat > "$FAKEBIN/gh" <<'GHEOF'
#!/usr/bin/env bash
method=GET
endpoint=""
body=""
while (($#)); do
  case "$1" in
    api) shift ;;
    -X) method="$2"; shift 2 ;;
    -f)
      case "$2" in body=*) body="${2#body=}" ;; esac
      shift 2
      ;;
    -F) shift 2 ;;
    --jq) shift 2 ;;
    --paginate|--slurp) shift ;;
    *)
      if [[ -z "$endpoint" ]]; then endpoint="$1"; fi
      shift
      ;;
  esac
done

if [[ "$endpoint" == user ]]; then
  [[ ! -f "$AUTH_FAIL" ]] || exit 1
  cat "$CURRENT_USER_FILE"
  exit 0
fi

if [[ "$method" == GET && "$endpoint" == "repos/owner/repo/pulls/1/comments" ]]; then
  [[ ! -f "$SCAN_FAIL" ]] || { echo "scan failed" >&2; exit 1; }
  cat "$REMOTE_COMMENTS"
  exit 0
fi

if [[ "$method" == GET && "$endpoint" == "repos/owner/repo/issues/1/comments" ]]; then
  echo '[[]]'
  exit 0
fi

if [[ "$method" == GET && "$endpoint" == "repos/owner/repo/pulls/1/reviews" ]]; then
  cat "$REMOTE_REVIEWS"
  exit 0
fi

if [[ "$method" == GET && "$endpoint" == graphql ]]; then
  jq '
    [.[][]] as $comments |
    [$comments[] | select(.in_reply_to_id == null) |
      . as $root |
      {id: ("thread-" + ($root.id | tostring)), isResolved: false,
       comments: {
         nodes: ([{databaseId:$root.id}] +
           [$comments[] | select(.in_reply_to_id == $root.id) | {databaseId:.id}]),
         pageInfo: {hasNextPage:false,endCursor:null}}}] |
    {data:{repository:{pullRequest:{reviewThreads:{nodes:.,pageInfo:{hasNextPage:false,endCursor:null}}}}}}
  ' "$REMOTE_COMMENTS"
  exit 0
fi

current_user=$(cat "$CURRENT_USER_FILE")
jq -cn --arg method "$method" --arg endpoint "$endpoint" --arg body "$body" \
  '{method:$method,endpoint:$endpoint,body:$body}' >> "$MUTATION_LOG"

if [[ "$method" == POST && "$endpoint" == repos/owner/repo/pulls/1/comments/*/replies ]]; then
  [[ ! -f "$POST_FAIL" ]] || exit 1
  root="${endpoint%/replies}"
  root="${root##*/}"
  jq --arg body "$body" --arg user "$current_user" --argjson root "$root" '
    .[0] += [{id:999,user:{login:$user},body:$body,path:"a.ts",line:1,
      pull_request_review_id:888,in_reply_to_id:$root,created_at:"2026-09-21T10:01:00Z"}]
  ' "$REMOTE_COMMENTS" > "$REMOTE_COMMENTS.next"
  mv "$REMOTE_COMMENTS.next" "$REMOTE_COMMENTS"
  jq --arg user "$current_user" '
    .[0] += [{id:888,user:{login:$user},body:"",state:"COMMENTED",
      submitted_at:"2026-09-21T10:01:00Z"}]
  ' "$REMOTE_REVIEWS" > "$REMOTE_REVIEWS.next"
  mv "$REMOTE_REVIEWS.next" "$REMOTE_REVIEWS"
  echo '{"id":999}'
  exit 0
fi

if [[ "$method" == PATCH && "$endpoint" == repos/owner/repo/pulls/comments/* ]]; then
  [[ ! -f "$PATCH_FAIL" ]] || exit 1
  comment_id="${endpoint##*/}"
  jq --arg body "$body" --argjson id "$comment_id" '
    map(map(if .id == $id then .body = $body else . end))
  ' "$REMOTE_COMMENTS" > "$REMOTE_COMMENTS.next"
  mv "$REMOTE_COMMENTS.next" "$REMOTE_COMMENTS"
  jq -cn --argjson id "$comment_id" '{id:$id}'
  exit 0
fi

echo "unmocked: $method $endpoint" >&2
exit 99
GHEOF
  chmod +x "$FAKEBIN/gh"
  export PATH="$FAKEBIN:$PATH"
  SCRIPT="${SCRIPTS}/reply_pr_comments.sh"
  BODY="$TMP/body.md"
  printf '<!-- pr-review-loop-reply -->\nnot changed in this review: out of scope\n' > "$BODY"
}

teardown() { rm -rf "$TMP"; }

run_reply_artifact_lifecycle() {
  local iteration="$1"
  local completed=$((iteration - 1))
  local state="$TMP/state-$iteration.json"
  local state_before="$TMP/state-before-$iteration.json"
  local original="$TMP/original-$iteration.json"
  local final="$TMP/final-$iteration.json"
  local packet="$TMP/packet-$iteration.json"

  : > "$MUTATION_LOG"
  cat > "$REMOTE_COMMENTS" <<'JSON'
[[{"id":10,"user":{"login":"ordinary-reviewer"},"body":"ordinary inline feedback","path":"fixture.py","line":2,"pull_request_review_id":77,"created_at":"2026-09-21T10:00:00Z"}]]
JSON
  cat > "$REMOTE_REVIEWS" <<'JSON'
[[{"id":77,"user":{"login":"ordinary-reviewer"},"body":"ordinary review body","state":"COMMENTED","submitted_at":"2026-09-21T10:00:00Z"}]]
JSON
  jq -n --argjson completed "$completed" '
    def comments: {fetch_error:null,issue_comments:[],review_comments:[],reviews:[],review_threads:[]};
    def panel: {mode:"full",ran:["tests"],skipped:[],gate_relevant:[],gate_fail_open:[],open_blocker_carryover:[]};
    def adversary: {reviewer:"adversary",verdict:"approve",findings:[],evidence:{files_read:["fixture.py"]}};
    {iteration:$completed,max_iterations:15,status:"running",dry_run:false,
     initial_head_sha:"reviewed-head",approvers_required_list:["tests"],comment_ledger:[],
     history:[range(1;$completed + 1) as $i |
       {iteration:$i,head_sha_before:"reviewed-head",head_sha_after:"reviewed-head",
        findings:[],ci_status:"skipped",panel_selection:panel,
        reviewers_completed:["tests"],reviewer_errors:[],adversary:adversary,
        human_comments:comments}]}
  ' > "$state"

  run bash "$SCRIPTS/fetch_pr_comments.sh" owner repo 1 author
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" > "$original"
  jq -e '
    .fetch_error == null and
    [.review_threads[].root_comment_id] == ["10"] and
    .review_threads[0].has_reply == false' "$original"
  cp "$state" "$state_before"

  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 0 ]
  cmp "$state_before" "$state"
  jq -e '.[][] | select(.id == 999) | .pull_request_review_id == 888 and .in_reply_to_id == 10' \
    "$REMOTE_COMMENTS"

  run python3 "$SCRIPTS/pr_loop_state.py" resume-decision --state "$state" \
    --current-head reviewed-head --remote-head reviewed-head
  [ "$status" -eq 0 ]
  echo "$output" | jq -e --argjson iteration "$iteration" '
    .terminal_status == null and .next_iteration == $iteration'
  cmp "$state_before" "$state"

  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 0 ]
  [ "$(wc -l < "$MUTATION_LOG" | tr -d ' ')" -eq 1 ]
  jq -e '[.[][] | select(.id == 888)] | length == 1' "$REMOTE_REVIEWS"
  cmp "$state_before" "$state"

  jq -n --slurpfile original "$original" '
    {entry:{head_sha_before:"reviewed-head",head_sha_after:"reviewed-head",
      findings:[],ci_status:"skipped",
      panel_selection:{mode:"full",ran:["tests"],skipped:[],gate_relevant:[],gate_fail_open:[],open_blocker_carryover:[]},
      reviewers_completed:["tests"],reviewer_errors:[],
      adversary:{reviewer:"adversary",verdict:"approve",findings:[],evidence:{files_read:["fixture.py"]}},
      human_comments:$original[0]},comment_updates:[]}
  ' > "$packet"
  run python3 "$SCRIPTS/pr_loop_state.py" append-history --state "$state" --input-json - < "$packet"
  [ "$status" -eq 2 ]
  cmp "$state_before" "$state"

  jq '.comment_updates = [{id:"10",source:"review_comment",disposition:"deferred",
    reason:"ordinary feedback remains open",replied_at:"2026-09-21T10:02:00Z"}]' \
    "$packet" > "$TMP/packet-next-$iteration.json"
  mv "$TMP/packet-next-$iteration.json" "$packet"
  run python3 "$SCRIPTS/pr_loop_state.py" append-history --state "$state" --input-json - < "$packet"
  [ "$status" -eq 0 ]
  jq -e --argjson iteration "$iteration" --slurpfile original "$original" '
    .iteration == $iteration and
    (.history | length) == $iteration and
    .history[-1].human_comments == $original[0] and
    .comment_ledger == [{id:"10",source:"review_comment",disposition:"deferred",
      reason:"ordinary feedback remains open",replied_at:"2026-09-21T10:02:00Z"}]' "$state"

  run bash "$SCRIPTS/fetch_pr_comments.sh" owner repo 1 author
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" > "$final"
  jq -e '
    .fetch_error == null and
    ([.reviews[] | select(.id == "888" and .loop_reply_artifact == true)] | length) == 1 and
    .review_threads[0].has_reply == true and
    .review_threads[0].replies == []' "$final"
  jq -e '.[][] | select(.id == 999) | .pull_request_review_id == 888' "$REMOTE_COMMENTS"

  jq -n --argjson iteration "$iteration" --slurpfile comments "$final" '
    {phase:"completion",iteration:$iteration,comments:$comments[0],
     current_head:"reviewed-head",remote_head:"reviewed-head"}' > "$TMP/completion-$iteration.json"
  run python3 "$SCRIPTS/check_exit_conditions.py" --state "$state" < "$TMP/completion-$iteration.json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.terminal_status == null and .continue_full_panel == false'
}

@test "posts once updates the same reply once and then performs no mutation" {
  local first_body second_body
  first_body=$(cat "$BODY")

  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 0 ]
  jq -e --arg body "$first_body" '
    .method == "POST" and
    .endpoint == "repos/owner/repo/pulls/1/comments/10/replies" and
    .body == $body' "$MUTATION_LOG"
  jq -e --arg body "$first_body" '
    ([.[][] | select((.body // "") | startswith("<!-- pr-review-loop-reply -->"))] | length) == 1 and
    (.[][] | select(.id == 999) | .body) == $body' "$REMOTE_COMMENTS"

  printf '<!-- pr-review-loop-reply -->\naddressed in new-sha with exact body\n' > "$BODY"
  second_body=$(cat "$BODY")
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 0 ]
  jq -s -e --arg first "$first_body" --arg second "$second_body" '
    length == 2 and
    .[0] == {method:"POST",endpoint:"repos/owner/repo/pulls/1/comments/10/replies",body:$first} and
    .[1] == {method:"PATCH",endpoint:"repos/owner/repo/pulls/comments/999",body:$second}' \
    "$MUTATION_LOG"
  jq -e --arg body "$second_body" '
    ([.[][] | select((.body // "") | startswith("<!-- pr-review-loop-reply -->"))] | length) == 1 and
    (.[][] | select(.id == 999) | .body) == $body' "$REMOTE_COMMENTS"

  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 0 ]
  [ "$(wc -l < "$MUTATION_LOG" | tr -d ' ')" -eq 2 ]
  jq -e --arg body "$second_body" '.[][] | select(.id == 999) | .body == $body' "$REMOTE_COMMENTS"
}

@test "posts when an existing reply under the thread is not a marker reply" {
  cat > "$REMOTE_COMMENTS" <<'JSON'
[[{"id":10,"user":{"login":"reviewer"},"body":"root"},{"id":56,"user":{"login":"human"},"body":"thanks","in_reply_to_id":10}]]
JSON
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 0 ]
  jq -e -s 'length == 1 and .[0].method == "POST"' "$MUTATION_LOG"
}

@test "an owned marker on a later page is updated and then reused" {
  cat > "$REMOTE_COMMENTS" <<'JSON'
[
  [{"id":10,"user":{"login":"reviewer"},"body":"root"}],
  [{"id":55,"user":{"login":"loop-author"},"body":"<!-- pr-review-loop-reply -->\nold body","in_reply_to_id":10}]
]
JSON
  printf '<!-- pr-review-loop-reply -->\nnew body from later page\n' > "$BODY"
  local expected
  expected=$(cat "$BODY")
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 0 ]
  jq -e -s --arg body "$expected" '
    length == 1 and .[0] ==
      {method:"PATCH",endpoint:"repos/owner/repo/pulls/comments/55",body:$body}' "$MUTATION_LOG"
  jq -e --arg body "$expected" '.[][] | select(.id == 55) | .body == $body' "$REMOTE_COMMENTS"

  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 0 ]
  [ "$(wc -l < "$MUTATION_LOG" | tr -d ' ')" -eq 1 ]
}

@test "a marker on the root itself is never selected as the PATCH target" {
  cat > "$REMOTE_COMMENTS" <<'JSON'
[[{"id":10,"user":{"login":"loop-author"},"body":"<!-- pr-review-loop-reply -->\nroot text"}]]
JSON
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 0 ]
  jq -e -s '
    length == 1 and .[0].method == "POST" and
    .[0].endpoint == "repos/owner/repo/pulls/1/comments/10/replies"' "$MUTATION_LOG"
  jq -e '([.[][] | select(.id == 10)] | length) == 1 and ([.[][] | select(.id == 999)] | length) == 1' \
    "$REMOTE_COMMENTS"
}

@test "a foreign marker fails without editing or posting" {
  cat > "$REMOTE_COMMENTS" <<'JSON'
[[{"id":10,"body":"root"},{"id":55,"user":{"login":"someone-else"},"body":"<!-- pr-review-loop-reply -->\nforeign","in_reply_to_id":10}]]
JSON
  cp "$REMOTE_COMMENTS" "$TMP/before.json"
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 1 ]
  [ ! -s "$MUTATION_LOG" ]
  cmp "$TMP/before.json" "$REMOTE_COMMENTS"
}

@test "duplicate owned markers fail without editing or posting" {
  cat > "$REMOTE_COMMENTS" <<'JSON'
[[{"id":10,"body":"root"},{"id":55,"user":{"login":"loop-author"},"body":"<!-- pr-review-loop-reply -->\none","in_reply_to_id":10},{"id":56,"user":{"login":"loop-author"},"body":"<!-- pr-review-loop-reply -->\ntwo","in_reply_to_id":10}]]
JSON
  cp "$REMOTE_COMMENTS" "$TMP/before.json"
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 1 ]
  [ ! -s "$MUTATION_LOG" ]
  cmp "$TMP/before.json" "$REMOTE_COMMENTS"
}

@test "a marker with missing ownership fails without editing or posting" {
  cat > "$REMOTE_COMMENTS" <<'JSON'
[[{"id":10,"body":"root"},{"id":55,"body":"<!-- pr-review-loop-reply -->\nunknown owner","in_reply_to_id":10}]]
JSON
  cp "$REMOTE_COMMENTS" "$TMP/before.json"
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 1 ]
  [ ! -s "$MUTATION_LOG" ]
  cmp "$TMP/before.json" "$REMOTE_COMMENTS"
}

@test "authentication failure exits 1 before scanning or mutating" {
  touch "$AUTH_FAIL"
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 1 ]
  [ ! -s "$MUTATION_LOG" ]
  [[ "$output" == *"cannot determine authenticated user"* ]]
}

@test "PATCH failure exits 1 and preserves the prior reply body" {
  cat > "$REMOTE_COMMENTS" <<'JSON'
[[{"id":10,"body":"root"},{"id":55,"user":{"login":"loop-author"},"body":"<!-- pr-review-loop-reply -->\nprior body","in_reply_to_id":10}]]
JSON
  touch "$PATCH_FAIL"
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 1 ]
  jq -e -s 'length == 1 and .[0].method == "PATCH" and .[0].endpoint == "repos/owner/repo/pulls/comments/55"' \
    "$MUTATION_LOG"
  jq -e '.[][] | select(.id == 55) | .body == "<!-- pr-review-loop-reply -->\nprior body"' \
    "$REMOTE_COMMENTS"
}

@test "POST failure exits 1 without adding a marker reply" {
  touch "$POST_FAIL"
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 1 ]
  jq -e -s 'length == 1 and .[0].method == "POST"' "$MUTATION_LOG"
  jq -e '[.[][] | select((.body // "") | startswith("<!-- pr-review-loop-reply -->"))] | length == 0' \
    "$REMOTE_COMMENTS"
}

@test "usage error when body file missing" {
  run bash "$SCRIPT" owner repo 1 10 "$TMP/nope.md"
  [ "$status" -eq 2 ]
}

@test "missing or empty arguments are usage errors" {
  run bash "$SCRIPT" owner repo 1 10
  [ "$status" -eq 2 ]
  [[ "$output" == *"usage:"* ]]
  run bash "$SCRIPT" owner "" 1 10 "$BODY"
  [ "$status" -eq 2 ]
  run bash "$SCRIPT" --print-existing owner repo 1
  [ "$status" -eq 2 ]
  [ ! -s "$MUTATION_LOG" ]
}

@test "usage error and no mutation when body first line is not the reply marker" {
  printf 'no marker on this line\nsome reply text\n' > "$TMP/nomarker.md"
  run bash "$SCRIPT" owner repo 1 10 "$TMP/nomarker.md"
  [ "$status" -eq 2 ]
  [ ! -s "$MUTATION_LOG" ]
}

@test "missing gh binary exits 7" {
  rm "$FAKEBIN/gh"
  PATH="$FAKEBIN" run /bin/bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 7 ]
}

@test "scan fetch failure stops without posting" {
  touch "$SCAN_FAIL"
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 1 ]
  [ ! -s "$MUTATION_LOG" ]
  [[ "$output" == *"thread scan failed"* ]]
}

@test "scan parse failure stops without posting and reports failure" {
  echo '[[42]]' > "$REMOTE_COMMENTS"
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 1 ]
  [ ! -s "$MUTATION_LOG" ]
  [[ "$output" == *"jq parse failed"* ]]
}

@test "missing comment response pages stop without posting" {
  echo '[]' > "$REMOTE_COMMENTS"
  run bash "$SCRIPT" owner repo 1 10 "$BODY"
  [ "$status" -eq 1 ]
  [ ! -s "$MUTATION_LOG" ]
}

@test "print-existing returns the owned marker reply without writing" {
  cat > "$REMOTE_COMMENTS" <<'JSON'
[
  [{"id":10,"user":{"login":"reviewer"},"body":"root"}],
  [{"id":55,"user":{"login":"loop-author"},"body":"<!-- pr-review-loop-reply -->\nprior body","in_reply_to_id":10,"html_url":"https://github.com/owner/repo/pull/1#discussion_r55"}]
]
JSON
  run bash "$SCRIPT" --print-existing owner repo 1 10
  [ "$status" -eq 0 ]
  [ "$output" = '{"id":55,"body":"<!-- pr-review-loop-reply -->\nprior body","html_url":"https://github.com/owner/repo/pull/1#discussion_r55"}' ]
  [ ! -s "$MUTATION_LOG" ]
}

@test "print-existing prints null when the thread has no marker reply" {
  cat > "$REMOTE_COMMENTS" <<'JSON'
[[{"id":10,"user":{"login":"loop-author"},"body":"<!-- pr-review-loop-reply -->\nroot text"},{"id":56,"user":{"login":"loop-author"},"body":"thanks","in_reply_to_id":10}]]
JSON
  run bash "$SCRIPT" --print-existing owner repo 1 10
  [ "$status" -eq 0 ]
  [ "$output" = "null" ]
  [ ! -s "$MUTATION_LOG" ]
}

@test "print-existing rejects a foreign marker reply" {
  cat > "$REMOTE_COMMENTS" <<'JSON'
[[{"id":10,"body":"root"},{"id":55,"user":{"login":"someone-else"},"body":"<!-- pr-review-loop-reply -->\nforeign","in_reply_to_id":10}]]
JSON
  run bash "$SCRIPT" --print-existing owner repo 1 10
  [ "$status" -eq 1 ]
  [[ "$output" == *"foreign or duplicate marker replies"* ]]
  [ ! -s "$MUTATION_LOG" ]
}

@test "reply artifact lifecycle completes iteration 1 without restarting the panel" {
  run_reply_artifact_lifecycle 1
}

@test "reply artifact lifecycle completes iteration 15 without exhausting the budget" {
  run_reply_artifact_lifecycle 15
}
