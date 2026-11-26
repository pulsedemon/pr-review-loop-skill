# Labeling protocol

How to label findings in `tools/recall-harness/labels.csv`.

## CSV columns

```
owner,repo,pr,bucket,finding_id,label,notes
```

- `owner`: GitHub owner/org (e.g. `pulsedemon`, `acme`).
- `repo`: repository name (e.g. `pr-review-loop`, `web`).
- `pr`: PR number (integer).
- `bucket`: one of: `unmatched`, `unanchored_external`, `unanchored_loop`, `matched_sample`, `loop_unmatched`.
- `finding_id`: 12-char hex hash, stable across A1/A2 re-runs. Copy it from the corresponding JSONL file. A2 writes none for `unanchored_external` and `unanchored_loop`, so hash the entry from the corpus file's `external_findings` or `loop_findings_unanchored`:

  ```bash
  python3 -c 'import json, sys; sys.path.insert(0, "tools/recall-harness"); from _shared import finding_id; print(finding_id(json.loads(sys.argv[1])))' '<entry JSON>'
  ```

- `label`: one of the labels in the section matching `bucket`.
- `notes`: Explain the judgment with enough code context to revisit it: the defect behind a `real_miss`, why a finding is useful, or why it is wrong or low-value. For example, "coverage wish on an error branch that already fails loudly" is checkable; "not useful" is not. Include ambiguity and related findings. Quote fields containing commas so the CSV retains the complete note; `tools/recall-harness/tests/test_version_and_schema_guards.py::test_committed_labels_rows_have_no_overflow_field` checks this.

One row per finding-bucket combination. `labels.csv` and `corpus-manifest.csv` are the committed artifacts: `REPORT.md` is regenerated from them and is not committed. `owner` and `repo` are required so PRs from different repos can share PR numbers without colliding.

## Label sets

### `bucket = unmatched` (the primary candidate-miss bucket)

External findings that A2 did NOT match to a loop finding. Apply ONE of:

- `real_miss`: concrete, actionable, in-scope finding the panel should have caught. Has a clear "the panel was wrong to approve this PR without flagging this" quality. Test: would you merge a follow-up PR that fixes only this finding?
- `noise`: vague, low-signal, or "consider X" commentary the panel was right to skip. Examples: "this could be more idiomatic," "consider adding a comment here," findings that don't survive a 30-second review of the actual code.
- `out_of_scope`: finding that violates the panel's scope-discipline rule. Examples: consistency with patterns elsewhere in the repo not touched by the PR; style preferences not in the PR description or linked ticket; refactor suggestions for unrelated code. The panel was correct to filter this out: the finding is a miss only by Copilot's loose standard, not by the loop's.
- `unrecoverable`: finding that requires runtime, deploy, repo-history, or production-data context the panel structurally cannot see. Examples: "this query is slow in prod" (no panel persona has access to prod metrics); "this conflicts with branch X" (no panel persona reads other branches). Real misses but not fixable by changing the panel.

### `bucket = unanchored_external`

External findings without a file:line anchor (Copilot summary-level reviews, etc.). These stay in the unanchored analysis buckets and do not feed the matcher. Apply ONE of:

- `unanchored_real_miss`: actionable in-scope finding even without a file:line anchor. Rare but possible.
- `unanchored_noise`: vague, low-signal, OR unrecoverable. (Collapsed because unanchored-and-unrecoverable adds no analytic value over unanchored-and-noise.)
- `unanchored_out_of_scope`: scope-discipline violation, same criteria as anchored `out_of_scope`.

### `bucket = unanchored_loop`

Loop findings parsed without a file:line anchor (e.g. CI-derived items). Apply ONE of:

- `unanchored_loop_keep`: useful informational content in the loop's summary.
- `unanchored_loop_drop`: wasn't worth surfacing; suggests a template change in a future PR.

### `bucket = matched_sample` (matcher quality spot-check)

A4 deterministically samples 10% (min 3) of the matched pairs in `matched/<owner>/<repo>/pr-<N>.jsonl` (written by A2). Score each pair:

- `matched_true`: the external and loop findings really refer to the same issue.
- `matched_false`: the pair should not have been made. Two cases: a matcher false-positive, where the findings are unrelated but happened to share a file and overlapping vocabulary; or a loop side that is not a panel finding at all, e.g. an `addressed:` / `deferred:` disposition line. REPORT.md surfaces the `matched_false` rate across judged sampled pairs; rates above `MATCHED_FALSE_WARN_THRESHOLD` in `tools/recall-harness/report.py` flag for matcher-tuning before trusting the unmatched-driven groups.

**A post-edit echo is still `matched_true`.** The label answers "do these describe the same issue", not "did the panel get there first": matching measures review overlap. So a bullet added to the summary after the reviewer comment it duplicates is a true pair, recorded with a note saying independence is unestablished.

Check before crediting one as a catch. `loop_summary_created_at` / `loop_summary_edited_at` record whether the summary was edited; when it was, the pre-edit revision is only reachable through `gh api graphql` → `userContentEdits`, because A1 collects the current body. The distinction matters for precision, where corroborated pairs count toward the numerator.

### `bucket = loop_unmatched` (the precision bucket)

Anchored loop findings no external reviewer corroborated, written by A2 to `loop_unmatched/<owner>/<repo>/pr-<N>.jsonl`.

**Non-corroboration is not evidence of a false positive.** Copilot has its own recall problem, so these are judged by hand against the diff and never inferred from the matched/unmatched split. Apply ONE of:

- `loop_true_positive`: correct and worth raising.
- `loop_false_positive`: wrong on the facts. Requires reading the code and confirming the claim is false. Correct-but-trivial is not this.
- `loop_low_value`: factually correct, not worth anyone's attention. Noisy, not wrong.
- `loop_unjudgeable`: needs context the labeler lacks. Excluded from the denominator.

Keeping `loop_low_value` separate matters: "said something true but boring" and "said something false" imply different fixes (raise the severity bar vs. fix the persona's reasoning).

Factual precision is `corroborated + loop_true_positive + loop_low_value` over `corroborated + loop_true_positive + loop_false_positive + loop_low_value`, always printed with the share of the population judged. Corroborated pairs count as true positives: an issue an external reviewer also raised is real. That is a claim about the issue, not about who found it first. See the post-edit echo note above.

The useful rate covers manually judged, uncorroborated loop findings: `loop_true_positive` divided by `loop_true_positive + loop_low_value + loop_false_positive`. It excludes corroborated findings because overlap does not establish usefulness. The report shows `n/a` when there are no manual judgments. Manual judgment coverage divides that judged count by the same population including unjudgeable and unlabeled findings; an absent population is `n/a`.

## Workflow

1. Run A1 + A2.
2. Open `labels.csv` and for each new row needed (from `unmatched/<owner>/<repo>/pr-<N>.jsonl`, `matched/<owner>/<repo>/pr-<N>.jsonl`, `loop_unmatched/<owner>/<repo>/pr-<N>.jsonl`, and the corpus files for the unanchored buckets), add a row.
3. Apply the label. Use `notes` liberally when in doubt: future-you will thank you.
4. Run A4 (`report.py`) to regenerate REPORT.md.
5. Commit `labels.csv` (and `corpus-manifest.csv` if you added PRs). `REPORT.md` is generated, not committed.

## Quick reference

| Finding looks like... | Label |
| --- | --- |
| A real bug the panel should have flagged | `real_miss` |
| Style nit Copilot loves and the panel is right to skip | `noise` |
| "Consider refactoring this unrelated file" | `out_of_scope` |
| "This is slow in prod" | `unrecoverable` |
| Two findings about the same line via shared vocabulary | `matched_false` |
| Loop side is an `addressed:` / `deferred:` disposition line | `matched_false` |
| Same issue, but the loop bullet postdates the comment | `matched_true` + note |
| Two findings genuinely about the same issue | `matched_true` |
| Loop finding that is correct and worth raising | `loop_true_positive` |
| Loop finding that is wrong on the facts | `loop_false_positive` |
| Loop finding that is true but not worth raising | `loop_low_value` |
