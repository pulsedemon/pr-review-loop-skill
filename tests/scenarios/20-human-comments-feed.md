# Scenario 20: Human-comments feed — filter, ordering, panel-only contract, metric counters

**Type:** Manual regression check covering `scripts/fetch_pr_comments.sh` and the §4a → §4b wiring.

## Setup

Pick any open PR with at least: one resolved review thread, one unresolved inline comment, one issue comment, one review with `state: CHANGES_REQUESTED`, and the loop's own prior summary comment (run the loop once first to plant it).

Capture a baseline:

```bash
bash scripts/fetch_pr_comments.sh "$OWNER" "$REPO" "$PR" "$PR_AUTHOR" > /tmp/hc.json
```

## Checks

1. **Loop-summary marker is dropped.** No element in `.issue_comments` has a body that starts with `<!-- pr-review-loop-summary -->`:

   ```bash
   jq -e '.issue_comments | all((.body // "") | startswith("<!-- pr-review-loop-summary -->") | not)' /tmp/hc.json
   ```

2. **Resolved-thread inline comments are dropped.** Build a list of comment ids in resolved threads and assert none appear in `.review_comments`:

   ```bash
   RESOLVED_IDS=$(jq -r '[.review_threads[] | select(.is_resolved) | .comment_ids[]] | join("\n")' /tmp/hc.json)
   for id in $RESOLVED_IDS; do
     jq -e ".review_comments | all(.id != \"$id\")" /tmp/hc.json || echo "LEAK: $id present"
   done
   ```

3. **Ordering: each visible array is ascending by `created_at` / `submitted_at`.**

   ```bash
   jq -e '.issue_comments  == (.issue_comments  | sort_by(.created_at))' /tmp/hc.json
   jq -e '.review_comments == (.review_comments | sort_by(.created_at))' /tmp/hc.json
   jq -e '.reviews         == (.reviews         | sort_by(.submitted_at))' /tmp/hc.json
   ```

4. **PR-author tagging.** At least one comment with `is_pr_author: true` is present if the PR author has commented. If not, this check is N/A.

5. **Panel-only contract: the §4d.0 adversary does NOT receive `human_comments`.** Run the loop and inspect the adversary's prompt input. The five-input list per `docs/adversary.md` should not include `human_comments`. Failing this check means change C5 leaked the block into §4d.0 — fix before merging.

6. **State capture.** After the loop runs one iteration, `.git/pr-loop/state.json` carries `human_comments` on `history[-1]`:

   ```bash
   jq -e '.history[-1].human_comments | type == "object"' .git/pr-loop/state.json
   ```

7. **Per-iteration metric record carries the three sub-counters.** The latest `iteration` line in `.git/pr-loop/metrics.jsonl` has `n_issue_comments`, `n_review_comments`, `n_reviews`. `n_reviews` excludes empty-body review records:

   ```bash
   LAST=$(grep '"kind":"iteration"' .git/pr-loop/metrics.jsonl | tail -1)
   echo "$LAST" | jq -e 'has("n_issue_comments") and has("n_review_comments") and has("n_reviews")'
   ```

8. **Failure mode: gh failure produces empty payload + `fetch_error`.** With `gh` missing entirely the script exits 7 (SETUP_ERROR). With `gh` present but a failing API it exits 0 with empty arrays and `fetch_error` set. Confirm whichever path applies.

9. **Loop-reply marker is dropped.** No element in `.issue_comments` or `.review_comments` has a body that starts with `<!-- pr-review-loop-reply -->` (the loop's own threaded replies must not re-enter the feed):

   ```bash
   jq -e '(.issue_comments + .review_comments) | all((.body // "") | startswith("<!-- pr-review-loop-reply -->") | not)' /tmp/hc.json
   ```

## Pass criterion

Checks 1, 2, 3, 6, 7, 9 pass. Check 4 is informational. Check 5 is the panel-only contract — regression here means C5 must be fixed. Check 8 depends on which failure mode you induce.

## Validation status

**Status:** `design_only`
**Missing evidence:** Add a dated end-to-end validation run or dedicated automation for the broader loop wiring around the human-comments feed.
