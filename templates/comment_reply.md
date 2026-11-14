# Inline comment reply bodies

Two neutral variants for replying to an inline review comment. The host picks
one, substitutes the placeholders, and writes the chosen body (starting with
the marker line) to a temp file passed to `scripts/reply_pr_comments.sh`.

Rules:

- The FIRST LINE of the posted body MUST be the marker `<!-- pr-review-loop-reply -->`
  so `scripts/fetch_pr_comments.sh` drops it on the next iteration.
- Neutral tone. No attribution, no tool/skill name, no "automated review" — same
  rule as the Step 5 summary comment (`docs/step5-summary.md`).
- Wording is run-scoped ("in this review"), never iteration-scoped ("this pass").
- One line of substance; link to the file/line for depth.

## Variant: addressed

<!-- pr-review-loop-reply -->
Updated in <short_sha> — <one-line description of the change that addresses this>.

## Variant: deferred

<!-- pr-review-loop-reply -->
Not changed in this review — <one-line reason: out of scope per linked ticket / disagreement with rationale / already correct / superseded>.
