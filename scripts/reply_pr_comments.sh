#!/usr/bin/env bash
# reply_pr_comments.sh <owner> <repo> <pr_number> <comment_id> <body_file>
#
# posts or updates a single marker-tagged reply to an inline review comment
# thread. idempotent via a mandatory thread scan: an unchanged reply owned by
# the authenticated user does nothing and exits 0. The scan uses its own gh
# fetch (NOT the loop's
# fetch_pr_comments.sh, which drops marker comments and so cannot see prior
# replies). This is the sole cross-run guard. state (comment_ledger) is
# ephemeral.
#
# Callers MUST ensure the body file's FIRST LINE is the reply marker so that
# fetch_pr_comments.sh drops it on the next iteration.
#
# <comment_id> MUST be the thread-ROOT review comment id: GitHub flattens
# threads so replies carry in_reply_to_id == root id, and the scan keys on
# that root id (not on a mid-thread reply's id).
#
# exit codes:
#   0 - posted, updated, or no-op (reply body is unchanged)
#   1 - authentication, reply scan, POST, or PATCH failed
#   2 - usage error (missing or empty argument, missing body file, or body
#       first line is not the reply marker)
#   7 - gh missing (SETUP_ERROR)

set -euo pipefail

if [[ $# -lt 5 || -z "$1" || -z "$2" || -z "$3" || -z "$4" || -z "$5" ]]; then
  echo "usage: reply_pr_comments.sh <owner> <repo> <pr_number> <comment_id> <body_file>" >&2
  exit 2
fi
OWNER="$1"
REPO="$2"
PR="$3"
COMMENT_ID="$4"
BODY_FILE="$5"

REPLY_MARKER='<!-- pr-review-loop-reply -->'

if ! command -v gh >/dev/null 2>&1; then
  echo "reply_pr_comments: gh CLI not installed" >&2
  exit 7
fi

if [[ ! -f "$BODY_FILE" ]]; then
  echo "reply_pr_comments: body file not found: $BODY_FILE" >&2
  exit 2
fi

# Enforce the self-trigger invariant in-script (symmetric to the body-file
# check above): the body's first line MUST be the reply marker so
# fetch_pr_comments.sh drops it next iteration. without the marker the loop
# re-ingests its own reply and re-replies every iteration until max_iterations.
if [[ "$(head -n 1 "$BODY_FILE")" != "$REPLY_MARKER" ]]; then
  echo "reply_pr_comments: body first line is not the reply marker: $BODY_FILE" >&2
  exit 2
fi

BODY=$(cat "$BODY_FILE")

ERR_FILE="$(mktemp)"
trap 'rm -f "$ERR_FILE"' EXIT

if ! CURRENT_USER="$(gh api user --jq .login 2>"$ERR_FILE")" || [[ -z "$CURRENT_USER" ]]; then
  echo "reply_pr_comments: cannot determine authenticated user: $(head -c 200 "$ERR_FILE")" >&2
  exit 1
fi

if ! SCAN_OUT="$(gh api "repos/$OWNER/$REPO/pulls/$PR/comments" --paginate --slurp 2>"$ERR_FILE")"; then
  echo "reply_pr_comments: thread scan failed: $(head -c 200 "$ERR_FILE")" >&2
  exit 1
fi

if ! MARKERS="$(printf '%s' "$SCAN_OUT" | jq -c --arg id "$COMMENT_ID" --arg rm "$REPLY_MARKER" '
    if type != "array" or length == 0 or any(.[]; type != "array") or
      any(.[][]; type != "object" or (.id | type != "number") or
        (has("body") | not) or (.body | type != "string" and type != "null"))
    then error("incomplete comment response") else
      [.[][] | select((.in_reply_to_id | tostring) == $id) |
        select((.body // "") | startswith($rm))]
    end
  ' 2>"$ERR_FILE")"; then
  echo "reply_pr_comments: thread scan jq parse failed: $(head -c 200 "$ERR_FILE")" >&2
  exit 1
fi

if ! printf '%s' "$MARKERS" | jq -e 'all(.[]; (.user.login | type) == "string")' >/dev/null 2>"$ERR_FILE"; then
  echo "reply_pr_comments: marker reply ownership is missing: $(head -c 200 "$ERR_FILE")" >&2
  exit 1
fi

if ! OWNED="$(printf '%s' "$MARKERS" | jq -c --arg user "$CURRENT_USER" '[.[] | select(.user.login == $user)]' 2>"$ERR_FILE")" ||
  ! MARKER_COUNT="$(printf '%s' "$MARKERS" | jq 'length' 2>"$ERR_FILE")" ||
  ! OWNED_COUNT="$(printf '%s' "$OWNED" | jq 'length' 2>"$ERR_FILE")"; then
  echo "reply_pr_comments: marker reply ownership parse failed: $(head -c 200 "$ERR_FILE")" >&2
  exit 1
fi

if [[ "$MARKER_COUNT" -ne "$OWNED_COUNT" ]] || [[ "$OWNED_COUNT" -gt 1 ]]; then
  echo "reply_pr_comments: foreign or duplicate marker replies require inspection" >&2
  exit 1
fi

if [[ "$OWNED_COUNT" -eq 1 ]]; then
  if printf '%s' "$OWNED" | jq -e --arg body "$BODY" '.[0].body == $body' >/dev/null; then
    exit 0
  fi
  if ! EXISTING_ID="$(printf '%s' "$OWNED" | jq -r '.[0].id' 2>"$ERR_FILE")"; then
    echo "reply_pr_comments: owned marker reply parse failed: $(head -c 200 "$ERR_FILE")" >&2
    exit 1
  fi
  if ! gh api -X PATCH "repos/$OWNER/$REPO/pulls/comments/$EXISTING_ID" \
    -f body="$BODY" >/dev/null 2>"$ERR_FILE"; then
    echo "reply_pr_comments: reply update failed for comment $EXISTING_ID: $(head -c 200 "$ERR_FILE")" >&2
    exit 1
  fi
else
  if ! gh api -X POST "repos/$OWNER/$REPO/pulls/$PR/comments/$COMMENT_ID/replies" \
    -f body="$BODY" >/dev/null 2>"$ERR_FILE"; then
    echo "reply_pr_comments: reply POST failed for comment $COMMENT_ID: $(head -c 200 "$ERR_FILE")" >&2
    exit 1
  fi
fi
