# comment handling

this document owns comment fetch, review-baseline, inline disposition, reply,
state-append, and completion mechanics. other documents link here instead of
restating them.

## fetch envelope

fetch the complete comment envelope at the start of every iteration:

```bash
PR_AUTHOR=$(jq -r '.pr_author // ""' "$(git rev-parse --git-dir)/pr-loop/state.json")
HUMAN_COMMENTS=$(bash "$SKILL_ROOT/scripts/fetch_pr_comments.sh" "$OWNER" "$REPO" "$PR_NUMBER" "$PR_AUTHOR")
```

the result is `{fetched_at, fetch_error, issue_comments, review_comments,
reviews, review_threads}`. `fetch_error` must be null. a missing page, malformed
REST response, incomplete GraphQL connection, or disagreement between the REST
comments and GraphQL threads makes the envelope incomplete and exits
`REVIEW_INCOMPLETE` before reviewers run. fetcher exit 2 for invalid usage and
exit 7 for missing `gh` map to `SETUP_ERROR`.

the fetcher applies these rules:

- `issue_comments` and `reviews` contain normalized external comments after
  marker filtering
- `review_comments` also omits resolved-thread content
- `review_threads[].root_comment` and `replies` retain normalized external text
  for resolved and unresolved threads
- `reviews` retains normalized review rows, including empty bodies. the optional
  `loop_reply_artifact:true` field marks exactly an empty `COMMENTED` review
  whose author matches the authenticated user and whose nonempty, complete raw
  inline group is linked by REST `pull_request_review_id` before resolved or
  marker filtering, and contains only that user's reserved-marker replies with
  no roots
- the summary marker is filtered from every collection. the reply marker is
  filtered from issue and inline comment content, while review bodies apply
  only the summary marker
- `has_reply` counts raw GraphQL replies before marker filtering
- an unavailable or failed optional identity lookup leaves the review ordinary.
  a discussion-fetch failure still makes the envelope incomplete
- bot logins, bot account types, and human-authored model-review comments stay
  in the envelope. `human_comments` is the historical field name, not a
  human-only filter

pass the whole envelope to each §4b panel reviewer as `human_comments`. the
§4d.0 adversary does not receive it. surface every unresolved or unanswered
thread to the panel, including a thread already in `comment_ledger` that needs
no new reply. the ledger narrows disposition work, not reviewer context.

## entry decision and reviewed baseline

before panel selection, ask the comments phase whether the original fetch
changed the reviewed discussion:

```bash
printf '%s' "$HUMAN_COMMENTS" |
  jq '{phase:"comments",comments:.}' |
  python3 "$SKILL_ROOT/scripts/check_exit_conditions.py" \
    --state "$(git rev-parse --git-dir)/pr-loop/state.json"
```

consume `continue_full_panel` before panel dispatch. when true, skip delta
selection and run the full panel for the current iteration.

the last completed `history[].human_comments` is the comparison baseline. an
absent or legacy baseline requires the full panel and fresh dispositions for
every currently required root. a root is required when its thread is
unresolved or has no raw reply.

comparison uses comment identity and normalized content only. the first
appearance of a verified `loop_reply_artifact` review is exempt from panel
restart, including replay of that same recorded artifact. existing review
identities always compare normalized body and state, so a transition to or from
empty `COMMENTED` still triggers review:

- a new or edited issue comment triggers review but has no inline ledger entry
- a new or edited review body or state triggers review, except for that first
  artifact appearance, but has no inline ledger entry
- a new or edited thread root or reply triggers review and fresh disposition
- reopening a resolved thread triggers review and fresh disposition
- ordering, timestamps, line movement, marker comments, and resolution without
  reopening do not trigger review
- deletion by itself does not trigger review

## disposition and reply

§4i runs disposition after §4h on the commit and push path and on §4d.1's
no-commit approval path. §4i has a third caller, §4c before the
`DRY_RUN_COMPLETE` exit; disposition does **not** run on that one. a dry run
reads the pr and must not write to it. incomplete reviews also skip disposition
and replies.

first recompute from the original reviewed `ENTRY`:

```bash
printf '%s' "$ENTRY" |
  jq '{phase:"comments",comments:.human_comments,
       code_changed:(.head_sha_before != .head_sha_after)}' |
  python3 "$SKILL_ROOT/scripts/check_exit_conditions.py" \
    --state "$(git rev-parse --git-dir)/pr-loop/state.json"
```

consume only `disposition_root_ids` here. the panel already reviewed this
envelope, so this call does not start another panel. the returned roots include
every required root missing from the ledger. when code changed, they also
include every ledgered root still present in the snapshot. this revalidation
catches a prior deferral that is now fixed and a prior fix that regressed even
when the thread text did not change.

make one current disposition for the whole thread using the reviewed head and
the root plus every reply in the original `ENTRY`.
the two dispositions are:

- `addressed`: current behavior resolves the thread's supported concern
- `deferred`: current behavior does not resolve it, or the original claim is
  false. give the factual reason

a responsive diff can prove a fix. an empty diff in a new run does not prove
that a concern is unaddressed. inspect the cited code and current behavior.
unchanged code is not a fix. after a code-changing iteration, call a thread
addressed only after its fix is committed and pushed, then cite that commit SHA.

before composing a reply, read the existing marker reply with the helper's
read mode. this read is separate from the filtered panel context and from the
helper's own rescan before it writes:

```bash
EXISTING_REPLY=$(bash "$SKILL_ROOT/scripts/reply_pr_comments.sh" --print-existing \
  "$OWNER" "$REPO" "$PR_NUMBER" "$ROOT_ID")
```

it prints the current user's marker reply as `{id, body, html_url}`, or `null`
when there is none, and writes nothing. exit 1 (failed authentication, fetch,
or parse, or a foreign or duplicate marker reply) maps to `REVIEW_INCOMPLETE`;
exits 2 and 7 map to `SETUP_ERROR`. on a fresh run, inspect the commit cited by
an existing reply and current behavior. when the reply remains valid, reuse its
exact body and SHA. do not replace a supported reply with an invented deferral
when verification fails. exit `REVIEW_INCOMPLETE` instead.

every body starts with `<!-- pr-review-loop-reply -->` and follows
`templates/comment_reply.md`. call the helper with the thread root id:

```bash
bash "$SKILL_ROOT/scripts/reply_pr_comments.sh" \
  "$OWNER" "$REPO" "$PR_NUMBER" "$ROOT_ID" "$BODY_FILE"
```

the helper independently authenticates and scans every REST page. it rejects
foreign or duplicate marker replies. an absent marker is posted, a changed
owned marker is patched, and an identical owned marker is a no-op. each exits
0. exit 1 maps to `REVIEW_INCOMPLETE`. exit 2 for invalid usage and exit 7 for
missing `gh` map to `SETUP_ERROR`. the loop never resolves or reopens a thread.

## atomic append

finish every required disposition and successful post, patch, or no-op before
writing state. create one fresh receipt per `disposition_root_ids` entry:
`{id, source:"review_comment", disposition, replied_at[, reason]}`. `reason` is
required only for `deferred`.

append the original reviewed snapshot and all receipts in one state operation:

```bash
printf '%s\n' "$ENTRY" "$COMMENT_UPDATES" |
  jq -s '{entry:.[0],comment_updates:.[1]}' |
  python3 "$SKILL_ROOT/scripts/pr_loop_state.py" append-history \
    --state "$(git rev-parse --git-dir)/pr-loop/state.json" --input-json -
```

the shared guard rejects an append that lacks a fresh receipt for any required
root. the helper atomically appends `ENTRY`, advances the iteration, and upserts
`comment_ledger` by root id with the latest successful disposition. run
`write_iteration_metric.sh` only after this append, as specified in `SKILL.md`.

on any disposition, reply, or append failure, do not advance the reviewed
baseline. an incomplete-review record-only path omits `human_comments` because
that snapshot was not dispositioned. a dry run performs no reply writes and
cannot certify reply completion.

## SUCCESS gate (§4d.1)

after the final CI wait and successful §4i append, fetch a new complete comment
envelope without writing it into `history[-1].human_comments`. then obtain both
heads immediately before the completion call. a failed comment fetch returns
`REVIEW_INCOMPLETE`; a failed head observation returns `SETUP_ERROR`.

```bash
set -euo pipefail
CURRENT_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD=$(gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER" --jq .head.sha)
printf '%s' "$FINAL_COMMENTS" |
  jq --argjson n "$ITERATION" --arg local "$CURRENT_HEAD" \
    --arg remote "$REMOTE_HEAD" \
    '{phase:"completion",iteration:$n,comments:.,
      current_head:$local,remote_head:$remote}' |
  python3 "$SKILL_ROOT/scripts/check_exit_conditions.py" \
    --state "$(git rev-parse --git-dir)/pr-loop/state.json"
```

`ITERATION` is the iteration just appended. the review and head conditions
are canonical in
[`exit-conditions.md`](exit-conditions.md#required-reviews-at-completion).

the completion result means:

- missing reviewed context or a failed required reply returns
  `REVIEW_INCOMPLETE`
- changed feedback starts another full-panel iteration when budget remains
- changed feedback at the cap returns `MAX_ITERATIONS`
- unchanged feedback with complete receipts permits `SUCCESS`
- a changed head returns `EXTERNAL_PUSH`

issue comments and review bodies never enter the inline ledger. they still
trigger review when added or edited and are acknowledged by the Step 5 summary.
inline dispositions in that summary come from the latest ledger values. see
[`step5-summary.md`](step5-summary.md).

## interruption safety

if a remote reply succeeds before the local append, the old baseline remains.
resume recomputes the same root, and the reply helper safely posts, patches, or
no-ops before the atomic append. an unrecorded push is different: existing
resume head validation returns `EXTERNAL_PUSH`. never guess, reset, or rebuild
state from that commit.
