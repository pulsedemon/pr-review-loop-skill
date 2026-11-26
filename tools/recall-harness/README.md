# recall-harness

Offline analysis tooling that measures where the pr-review-loop panel misses real issues on merged PRs. Not part of the loop's runtime contract: runs on demand. The corpus is namespaced by `<owner>/<repo>/pr-<N>` (directory-nested so owner or repo names containing `-` cannot collide on a flat filename) so PRs from multiple repos can sit side-by-side without collision; `labels.csv` carries the owner/repo columns to match.

## When to run

The repository starts with empty manifest and label files. Collect and label PRs you have permission to analyze when you want an evaluation report. This is optional; no historical private corpus ships with the skill.

## Workflow

```bash
# capture the discovery result before appending; a failed scan can print partial rows.
MANIFEST=tools/recall-harness/corpus-manifest.csv
if rows=$(python3 tools/recall-harness/find_loop_prs.py pulsedemon pr-review-loop-skill); then
  printf '%s\n' "$rows" | grep -vxF -f "$MANIFEST" >> "$MANIFEST"
fi

# manifest mode removes stale records after collecting the requested PRs.
python3 tools/recall-harness/collect_pr_corpus.py --manifest "$MANIFEST"

python3 tools/recall-harness/match_external.py

$EDITOR tools/recall-harness/labels.csv

python3 tools/recall-harness/report.py > tools/recall-harness/REPORT.md
git add tools/recall-harness/labels.csv tools/recall-harness/corpus-manifest.csv
```

Use the [labeling protocol](label.md) when editing labels. Commit the labels and manifest; keep the generated report and collected discussions private unless cleared for publication. To collect a date-based subset instead, use `--owner pulsedemon --repo pr-review-loop-skill --merged-since YYYY-MM-DD`; it is mutually exclusive with `--manifest`.

### In-flight PRs

Pass `--include-open` to `collect_pr_corpus.py` to collect not-yet-merged PRs alongside merged ones. In-flight records carry `is_open: true` and are excluded from merged-PR totals/per-repo/matcher-quality aggregates; `report.py` surfaces them in a dedicated `## In-flight PRs (excluded from totals)` section so the operator can review them without polluting frozen statistics. A2 (`match_external.py`) skips `is_open` records: no `matched/` or `unmatched/` JSONL is produced, and because A4 (`report.py`) samples `matched_sample` from those A2 outputs, no `matched_sample` rows appear for in-flight PRs either. There is nothing to label until they merge.

## Finding loop-run PRs

`find_loop_prs.py <owner> <repo>` prints manifest rows for every merged PR whose top-level
issue comments carry `<!-- pr-review-loop-summary -->`: the same signal the collector reads.
Output goes to stdout in manifest order so it appends straight onto `corpus-manifest.csv`;
progress and warnings go to stderr.

It pages the GraphQL API, pulling each PR's comments alongside its number so one request
covers 50 PRs. Discovery reads the comments directly because GitHub search can omit
comments containing the summary marker.

Only the first 100 comments of a PR are read. A marker past that boundary is missed, so a PR
with more comments than that is named on stderr and the script exits 3, so the row set it
printed may be short. Check that code before appending: a pipeline reports its last command's
status, so piping the rows straight into the manifest throws the 3 away (step 0 above shows
the shape that keeps it).

Pass `--checkout <path>` to cross-check a local clone's `<git-dir>/pr-loop/` archives. A PR with
archived loop state but no summary comment is a run that ended before Step 5; the script warns
about it and does not emit a row. A PR whose comments were truncated is left out of that
warning, since its marker may sit past the page that was read. That data stays out of the corpus deliberately: archives are
gitignored and machine-local (most manifested PRs have none), so rows drawn from them would
differ per checkout, and their pre-synthesis findings are not the shape the matcher compares.

## What `matched` means here

A2 does not use the loop's §4c dedupe rule. It scores `token_containment` (overlap over the smaller summary) at `CONTAINMENT_THRESHOLD`, within `HARNESS_LINE_WINDOW`, rather than Jaccard at `OVERLAP_THRESHOLD` within `LINE_WINDOW`.

The two comparisons serve different purposes. Section 4c deduplicates panel findings. The recall harness compares a loop summary with an external review comment, whose length and wording can differ. Token containment measures the overlap against the smaller token set; `MIN_CONTAINMENT_TOKENS` excludes short summaries with too little evidence for a useful match.

So a `matched` row means "the panel and an external reviewer raised the same issue", not "§4c would dedupe these two". Read the recall numbers as review overlap. `MIN_CONTAINMENT_TOKENS` guards the degenerate case where a short summary is trivially contained in a long one.

A1 reads the rendered summary comment, so changes to summary rendering can change the measured overlap without changing reviewer behavior. Compare the underlying findings across rendering changes before attributing a score change to a persona.

It does not mean the panel found the issue *first*. A1 parses the current summary body, and the loop edits that comment as the run progresses, so a bullet may postdate the reviewer comment it pairs with. `loop_summary_created_at` and `loop_summary_edited_at` record whether an edit happened; when one did, the pre-edit revision is only reachable through `gh api graphql` → `userContentEdits`. Bullets under a `**Reviewer comments:**` header are dispositions rather than findings and are dropped at parse time. An anchored bullet separates its `file:line` from the summary with either an em dash or a colon; both parse, and a parenthetical between the two (`(nit)`, `(foreign-symlink guard)`) is kept in the summary rather than stripped.

## What gets committed

- `labels.csv`: your labels are the artifact. Schema: `owner,repo,pr,bucket,finding_id,label,notes`. Keys (owner + repo + PR + bucket + finding hash) are stable across re-runs because A1 normalizes deterministically.
- `corpus-manifest.csv`: the canonical PR set (`owner,repo,pr`). `collect_pr_corpus.py --manifest` regenerates exactly this corpus; pytest tests assert every labeled PR and every collected corpus file appears here.

  The manifest is updated manually. The weekly workflow collects the live merged set, while `--manifest` collects the committed list. `check_manifest_drift.py` fails the weekly run when merged PRs are missing from the manifest and names them in its diagnostic.

  The committed manifest and labels start empty; populate them with your own cleared evaluation set. The collector also supports your own cross-repository manifests, but `--manifest` requires access to every listed repository and exits non-zero if one is unreachable. Keep private manifests and their generated corpora outside the published tree. The optional workflow authenticates with the repository's `GITHUB_TOKEN` and collects only this repository. It remains disabled until the maintainer chooses to collect a corpus.
- `label.md`: the labeling protocol document.
- `tools/recall-harness/tests/fixtures/orchestrator-review-sample.md`: a synthetic ORCHESTRATOR_REVIEW body that pins the FINDING-block parser; re-record only when the upstream format changes.

## What does not get committed

- `corpus/`, `unmatched/`, `matched/`, `loop_unmatched/`, `REPORT.md`: generated, regeneratable. `REPORT.md` is a view over `labels.csv` + the (gitignored, possibly private-repo) corpus, so it is machine-dependent; regenerate it on demand rather than committing it.

Matcher output directories are dedicated to generated JSONL. Publication briefly reserves each outer output directory with a sibling `.<name>.recall-lock` directory. If a process stops during publication, inspect retained `.recall-*/previous` backups and confirm the owner has exited before clearing its reservation.

## Evaluating changes

See [Evaluating reviewer changes](../../docs/editing-personas.md#evaluating-reviewer-changes)
for how to use recall evidence when changing the panel.

## Sources

Recognized external review tools live in the `EXTERNAL_REVIEW_TOOLS` registry in `tools/recall-harness/collect_pr_corpus.py`. Each entry pairs a set of GitHub logins with an optional body marker; the body marker is mandatory whenever the login is shared across many bots (e.g. `github-actions[bot]`) and must be omitted only when the login itself uniquely identifies the tool. To add a new external tool: append an `ExternalReviewTool(...)` entry to the registry and update this list. The first match wins, so put more specific entries first. The comment-walk loop in `collect_pr_corpus.py::collect_pr` calls `parse_orchestrator_findings` on every recognized tool's top-level issue comment; when the tool's `name` is in `STRUCTURED_FINDING_SOURCES` and the body advertises FINDING blocks (`<!--` followed by optional whitespace and case-insensitive `FINDING:`) but parsing yields none, the call site raises rather than falling back to a whole-body unanchored finding. Review-thread comments and top-level reviews from recognized tools are recorded through `normalize_external_comment` (or as unanchored summary entries) without FINDING-block parsing, but the same drift-probe guard fires at those venues too so an upstream change in posting venue cannot silently bypass it. If the new tool emits a *different* structured body format, add a new parser function and dispatch on `tool.name` at the call site, and add the tool's `name` to `STRUCTURED_FINDING_SOURCES` so the drift-vs-LGTM guard applies to it.

- **`copilot`**: GitHub Copilot. Logins: `Copilot`, `copilot-pull-request-reviewer`. No body marker (the logins are tool-specific). Inline review-thread comments are anchored via the API's `path`/`line` fields; top-level reviews are recorded as unanchored.
- **`orchestrator-review`**: in-house pr-review tools that post structured reviews as `github-actions[bot]` with a comment body beginning with `<!-- ORCHESTRATOR_REVIEW |`. Each comment can contain multiple findings; each finding is delimited by an HTML-comment block (`<!-- FINDING: <SEVERITY> | <file> | <agent> | L<start> | L<end> -->` followed by `<!-- TITLE: <title> -->`), parsed by `parse_orchestrator_findings`.
- **`pr-review-toolkit`**: not implemented. `source: "toolkit"` is reserved for it.
