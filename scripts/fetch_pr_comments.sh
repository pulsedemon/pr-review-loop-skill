#!/usr/bin/env bash
# fetch_pr_comments.sh <owner> <repo> <pr_number> <pr_author_login>
#
# pr_author_login is required (callers read it from state.json's pr_author,
# populated in scripts/state_init.sh). missing author surfaces as
# fetch_error: "pr_author_missing" with empty arrays.
#
# emits a single JSON object on stdout with these keys:
#   fetched_at, fetch_error, issue_comments, review_comments, reviews, review_threads
# fetched_at is an ISO-8601 UTC timestamp; fetch_error is null on success
# or a short string on partial failure (see empty_payload + emit_failure).
#
# filters applied:
#   - drop any comment whose body's FIRST LINE begins with the
#     "<!-- pr-review-loop-summary -->" marker
#   - drop any issue_comment or review_comment whose body's FIRST LINE begins
#     with the "<!-- pr-review-loop-reply -->" marker (loop-posted replies).
#     not applied to the reviews array, whose bodies are never inline replies.
#   - drop any inline review comment whose thread is_resolved == true
#   - keep pr-author comments; tag with is_pr_author: bool
#   - keep all review records regardless of state
#   - annotate verified reply-only reviews and retain them
#
# each review_comment carries in_reply_to_id (null for a thread root) and
# is_thread_root (bool). Callers reply only to thread roots. reply_pr_comments.sh
# keys its idempotency scan on the root id, so passing a non-root id would miss
# the loop's own prior reply and double-post.
#
# exit codes:
#   0 - success (including the "gh failed, emit empty payload" path)
#   7 - gh missing (SETUP_ERROR, same as fetch_pr.sh)

set -euo pipefail

OWNER="${1:?usage: fetch_pr_comments.sh <owner> <repo> <pr_number> <pr_author_login>}"
REPO="${2:?usage}"
PR="${3:?usage}"
AUTHOR="${4:-}"

if ! command -v gh >/dev/null 2>&1; then
  echo "fetch_pr_comments: gh CLI not installed" >&2
  exit 7
fi

FETCHED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

empty_payload() {
  local err="${1:-null}"
  jq -n --arg err "$err" --arg at "$FETCHED_AT" '{fetched_at:$at,fetch_error:$err,issue_comments:[],review_comments:[],reviews:[],review_threads:[]}'
}

# pr_author is required: scripts/state_init.sh persists it on init. if a
# caller omits it (or it failed to populate), tag every comment is_pr_author:false
# is the wrong default — surface the missing input loudly and let the panel see
# the fetch_error instead.
if [[ -z "$AUTHOR" ]]; then
  empty_payload "pr_author_missing"
  exit 0
fi

ERR_FILE=$(mktemp)
trap 'rm -f "$ERR_FILE"' EXIT

# emit empty_payload with the captured gh stderr (truncated to 200 chars)
# included in fetch_error so a sustained auth/rate-limit failure leaves a
# triage breadcrumb rather than a silent empty array. callers `exit 0` after
# this — emit_failure stays out of a subshell so exit propagates.
emit_failure() {
  local label="$1" err_excerpt
  err_excerpt=$(head -c 200 "$ERR_FILE")
  if [[ -n "$err_excerpt" ]]; then
    empty_payload "$label fetch failed: $err_excerpt"
  else
    empty_payload "$label fetch failed"
  fi
}

# --slurp wraps the per-page JSON arrays into an outer array `[[page1...],...]`
# so the captured stdout is a single valid JSON value for later stdin transforms.
: >"$ERR_FILE"
ISSUE_RAW=$(gh api "repos/$OWNER/$REPO/issues/$PR/comments" --paginate --slurp 2>"$ERR_FILE") || {
  emit_failure issue_comments
  exit 0
}
: >"$ERR_FILE"
REVIEW_COMMENTS_RAW=$(gh api "repos/$OWNER/$REPO/pulls/$PR/comments" --paginate --slurp 2>"$ERR_FILE") || {
  emit_failure review_comments
  exit 0
}
: >"$ERR_FILE"
REVIEWS_RAW=$(gh api "repos/$OWNER/$REPO/pulls/$PR/reviews" --paginate --slurp 2>"$ERR_FILE") || {
  emit_failure reviews
  exit 0
}

for RAW in "$ISSUE_RAW" "$REVIEW_COMMENTS_RAW" "$REVIEWS_RAW"; do
  if ! printf '%s' "$RAW" | jq -e '
    type == "array" and length > 0 and all(.[]; type == "array") and
    all(.[][]; type == "object" and (.id | type == "number") and
      has("body") and (.body | type == "string" or type == "null"))
  ' >/dev/null 2>&1; then
    empty_payload "comments incomplete REST data"
    exit 0
  fi
done

# REST omits resolution state, and each thread has its own comment cursor.
# shellcheck disable=SC2016
THREAD_QUERY='
  query($owner:String!,$repo:String!,$pr:Int!,$cursor:String){
    repository(owner:$owner,name:$repo){
      pullRequest(number:$pr){
        reviewThreads(first:100,after:$cursor){
          pageInfo{hasNextPage endCursor}
          nodes{id isResolved comments(first:100){
            pageInfo{hasNextPage endCursor} nodes{databaseId}
          }}
        }
      }
    }
  }'
# shellcheck disable=SC2016
COMMENT_QUERY='
  query($thread:ID!,$cursor:String!){
    node(id:$thread){... on PullRequestReviewThread{
      comments(first:100,after:$cursor){
        pageInfo{hasNextPage endCursor} nodes{databaseId}
      }
    }}
  }'

valid_connection() {
  jq -e '
    type == "object" and (.nodes | type == "array") and
    (.pageInfo.hasNextPage | type == "boolean") and
    (if .pageInfo.hasNextPage then
      (.pageInfo.endCursor | type == "string" and length > 0)
    else true end)
  ' >/dev/null 2>&1
}

fetch_graphql() {
  : >"$ERR_FILE"
  if ! GRAPHQL_RAW=$(gh api graphql "$@" 2>"$ERR_FILE"); then
    emit_failure review_threads
    return 1
  fi
  if ! printf '%s' "$GRAPHQL_RAW" | jq -e 'type == "object" and (has("errors") | not)' >/dev/null 2>&1; then
    empty_payload "review_threads graphql errors"
    return 1
  fi
}

THREADS_RAW='[]'
THREAD_CURSOR=''
THREAD_CURSORS='[]'
while :; do
  CURSOR_ARGS=()
  if [[ -n "$THREAD_CURSOR" ]]; then CURSOR_ARGS=(-f cursor="$THREAD_CURSOR"); fi
  fetch_graphql -F owner="$OWNER" -F repo="$REPO" -F pr="$PR" ${CURSOR_ARGS[@]+"${CURSOR_ARGS[@]}"} -f query="$THREAD_QUERY" || exit 0
  CONNECTION=$(printf '%s' "$GRAPHQL_RAW" | jq 'try .data.repository.pullRequest.reviewThreads catch null')
  if ! printf '%s' "$CONNECTION" | valid_connection; then
    empty_payload "review_threads incomplete data"
    exit 0
  fi
  while IFS= read -r THREAD; do
    if ! printf '%s' "$THREAD" | jq -e '
      (.id | type == "string" and length > 0) and
      (.isResolved | type == "boolean")
    ' >/dev/null 2>&1; then
      empty_payload "review_threads incomplete data"
      exit 0
    fi
    COMMENTS=$(printf '%s' "$THREAD" | jq '.comments')
    COMMENT_NODES='[]'
    COMMENT_CURSORS='[]'
    while :; do
      if ! printf '%s' "$COMMENTS" | valid_connection ||
        ! printf '%s' "$COMMENTS" | jq -e 'all(.nodes[]; .databaseId | type == "number")' >/dev/null 2>&1; then
        empty_payload "review_threads incomplete comments"
        exit 0
      fi
      COMMENT_NODES=$(printf '%s\n' "$COMMENT_NODES" "$COMMENTS" | jq -s '.[0] + .[1].nodes')
      [[ $(printf '%s' "$COMMENTS" | jq '.pageInfo.hasNextPage') == true ]] || break
      COMMENT_CURSOR=$(printf '%s' "$COMMENTS" | jq -r '.pageInfo.endCursor')
      if printf '%s' "$COMMENT_CURSORS" | jq -e --arg cursor "$COMMENT_CURSOR" 'index($cursor) != null' >/dev/null; then
        empty_payload "review_threads repeated comment cursor"
        exit 0
      fi
      COMMENT_CURSORS=$(printf '%s' "$COMMENT_CURSORS" | jq --arg cursor "$COMMENT_CURSOR" '. + [$cursor]')
      fetch_graphql -f thread="$(printf '%s' "$THREAD" | jq -r '.id')" -f cursor="$COMMENT_CURSOR" -f query="$COMMENT_QUERY" || exit 0
      COMMENTS=$(printf '%s' "$GRAPHQL_RAW" | jq 'try .data.node.comments catch null')
    done
    if [[ $(printf '%s' "$COMMENT_NODES" | jq 'length') == 0 ]]; then
      empty_payload "review_threads missing root comment"
      exit 0
    fi
    THREADS_RAW=$(printf '%s\n' "$THREADS_RAW" "$THREAD" "$COMMENT_NODES" | jq -s '
      .[0] as $prev |
      .[1] as $thread |
      .[2] as $comments |
      $prev + [$thread | .comments.nodes = $comments]
    ')
  done < <(printf '%s' "$CONNECTION" | jq -c '.nodes[]')
  [[ $(printf '%s' "$CONNECTION" | jq '.pageInfo.hasNextPage') == true ]] || break
  THREAD_CURSOR=$(printf '%s' "$CONNECTION" | jq -r '.pageInfo.endCursor')
  if printf '%s' "$THREAD_CURSORS" | jq -e --arg cursor "$THREAD_CURSOR" 'index($cursor) != null' >/dev/null; then
    empty_payload "review_threads repeated thread cursor"
    exit 0
  fi
  THREAD_CURSORS=$(printf '%s' "$THREAD_CURSORS" | jq --arg cursor "$THREAD_CURSOR" '. + [$cursor]')
done

RESOLVED_MAP=$(printf '%s' "$THREADS_RAW" | jq '[
  .[] | {key: (.comments.nodes[].databaseId | tostring), value: .isResolved}
] | from_entries')

SUMMARY_MARKER='<!-- pr-review-loop-summary -->'
REPLY_MARKER='<!-- pr-review-loop-reply -->'

# input shape is `[[page1...], [page2...]]` from gh api --paginate --slurp;
# .[][] flattens across pages.
normalize_issue() {
  jq --arg author "$AUTHOR" --arg sm "$SUMMARY_MARKER" --arg rm "$REPLY_MARKER" '
    [ .[][]
      | select((((.body // "") | startswith($sm)) or ((.body // "") | startswith($rm))) | not)
      | { id: (.id|tostring), author: .user.login, is_pr_author: (.user.login == $author),
          body: .body, created_at: .created_at, source: "issue_comment" }
    ] | sort_by(.created_at)
  '
}

normalize_review_comments() {
  jq --arg author "$AUTHOR" '
    [ .[][]
      | { id: (.id|tostring), author: .user.login, is_pr_author: (.user.login == $author),
          body: .body, file: .path, line: (.line // .original_line),
          review_id: (.pull_request_review_id|tostring),
          in_reply_to_id: (if .in_reply_to_id == null then null else (.in_reply_to_id|tostring) end),
          is_thread_root: (.in_reply_to_id == null),
          created_at: .created_at, source: "review_comment" }
    ] | sort_by(.created_at)
  '
}

normalize_reviews() {
  jq --arg author "$AUTHOR" --arg marker "$SUMMARY_MARKER" '
    [ .[][]
      | select(((.body // "") | startswith($marker)) | not)
      | { id: (.id|tostring), author: .user.login, is_pr_author: (.user.login == $author),
          body: (.body // ""), state: .state,
          submitted_at: (.submitted_at // .created_at // ""), source: "review" }
    ] | sort_by(.submitted_at)
  '
}

if ! ISSUE=$(echo "$ISSUE_RAW" | normalize_issue) ||
  ! ALL_RCMT=$(echo "$REVIEW_COMMENTS_RAW" | normalize_review_comments) ||
  ! REVS=$(echo "$REVIEWS_RAW" | normalize_reviews); then
  empty_payload "comments normalization failed"
  exit 0
fi
RCMT=$(printf '%s\n' "$ALL_RCMT" "$RESOLVED_MAP" | jq -s --arg sm "$SUMMARY_MARKER" --arg rm "$REPLY_MARKER" '
  .[0] as $comments |
  .[1] as $resolved |
  [$comments[] | select(($resolved[.id] // false) | not)
   | select((((.body // "") | startswith($sm)) or ((.body // "") | startswith($rm))) | not)]
')
if ! printf '%s\n' "$THREADS_RAW" "$ALL_RCMT" | jq -se '
  .[0] as $threads |
  (.[1] | map(.id)) as $ids |
  all($threads[].comments.nodes[];
    (.databaseId | tostring) as $id | $ids | index($id) != null)
' >/dev/null; then
  empty_payload "review_threads missing REST comment content"
  exit 0
fi
THREADS=$(printf '%s\n' "$THREADS_RAW" "$ALL_RCMT" | jq -s --arg sm "$SUMMARY_MARKER" --arg rm "$REPLY_MARKER" '
  .[0] as $threads |
  .[1] as $comments |
  ($comments | map({key: .id, value: .}) | from_entries) as $by_id |
  [$threads[] |
    (.comments.nodes[0].databaseId | tostring) as $root |
    ([.comments.nodes[1:][] | .databaseId | tostring] |
      map($by_id[.] | select((((.body // "") | startswith($sm)) or
        ((.body // "") | startswith($rm))) | not))) as $replies |
    {thread_id: .id, is_resolved: .isResolved,
     comment_ids: [.comments.nodes[].databaseId | tostring],
     root_comment_id: $root, root_comment: $by_id[$root],
     has_reply: (.comments.nodes | length > 1), replies: $replies}]
')
if ! printf '%s' "$THREADS" | jq -e 'all(.[]; .root_comment.is_thread_root == true)' >/dev/null; then
  empty_payload "review_threads missing root comment"
  exit 0
fi
if ! printf '%s\n' "$ALL_RCMT" "$THREADS" | jq -se '
  .[0] as $comments |
  .[1] as $threads |
  [$threads[].root_comment_id] as $roots |
  [$threads[].comment_ids[]] as $ids |
  all($comments[];
    (.id as $id | $ids | index($id) != null) and
    ((.in_reply_to_id // .id) as $root | $roots | index($root) != null))
' >/dev/null; then
  empty_payload "review_threads missing REST comment or root"
  exit 0
fi
THREADS=$(printf '%s' "$THREADS" | jq --arg sm "$SUMMARY_MARKER" --arg rm "$REPLY_MARKER" '
  [.[] | select((((.root_comment.body // "") | startswith($sm)) or
    ((.root_comment.body // "") | startswith($rm))) | not)]
')

CURRENT_USER=''
if printf '%s' "$ALL_RCMT" | jq -e --arg rm "$REPLY_MARKER" \
  'any(.[]; .in_reply_to_id != null and ((.body // "") | startswith($rm)))' >/dev/null; then
  if ! CURRENT_USER=$(
    gh api user \
      --jq '.login | select(type == "string" and length > 0)' 2>"$ERR_FILE"
  ); then
    CURRENT_USER=''
  fi
fi
if [[ -n "$CURRENT_USER" ]]; then
  if ! REVS=$(printf '%s\n' "$REVS" "$ALL_RCMT" | jq -s \
    --arg user "$CURRENT_USER" --arg rm "$REPLY_MARKER" '
      .[0] as $reviews |
      (.[1] | group_by(.review_id) |
        map({key: .[0].review_id, value: .}) | from_entries) as $groups |
      [$reviews[] | ($groups[.id] // []) as $linked |
        if .body == "" and .state == "COMMENTED" and .author == $user and
          ($linked | length > 0) and
          all($linked[]; .is_thread_root == false and .in_reply_to_id != null and
            .author == $user and ((.body // "") | startswith($rm)))
        then . + {loop_reply_artifact: true} else . end]
    '); then
    empty_payload 'comments normalization failed'
    exit 0
  fi
fi

printf '%s\n' "$ISSUE" "$RCMT" "$REVS" "$THREADS" | jq -s --arg at "$FETCHED_AT" '
  {fetched_at:$at, fetch_error:null, issue_comments:.[0], review_comments:.[1],
   reviews:.[2], review_threads:.[3]}
'
