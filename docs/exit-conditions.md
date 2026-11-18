# NO_PROGRESS and CI_STUCK mechanics

`scripts/check_exit_conditions.py` owns iteration boundaries, review and comment completion, and both comparisons. SKILL.md §4d and §4d.1 name the script and
link here rather than restating the rules, so a host does not have to reconstruct them and they
cannot drift from `scripts/finding_matcher.py`.

## Calling it

```bash
echo '{"blockers": [...]}' | python3 "$SKILL_ROOT/scripts/check_exit_conditions.py" --state "$(git rev-parse --git-dir)/pr-loop/state.json"
```

the comparison call sites send `blockers` from §4d or `ci_failed_checks` from
§4d.1 after `ci_wait.sh`. both live only in the orchestrator's context until
§4i appends them to `history[]`, which is why they arrive on stdin while the
lookback reads the state file.

the comparison output is `{"terminal_status": "NO_PROGRESS"|"CI_STUCK"|null,
"reason": "..."}`. phase calls additionally return `MAX_ITERATIONS`,
`REVIEW_INCOMPLETE`, or `EXTERNAL_PUSH`. comments returns
`disposition_root_ids` and `continue_full_panel`; completion includes
`continue_full_panel` when no terminal status applies. a `null` status means no
exit fires. exit code 2 is reserved for malformed input. the key matches the
`TERMINAL_STATUS` that `scripts/write_terminal_metric.sh` consumes, so the
value passes straight through to Step 5.

## iteration boundaries

send `{"phase":"entry"}` before every §4a. the helper uses completed
`state.iteration + 1` and returns `MAX_ITERATIONS` if it exceeds `max_iterations`.

send `phase:"comments"` after the entry fetch and again at §4i. comment
inputs, outputs, and the different consumers at those two calls are owned by
[`comment handling`](comment-handling.md).

send `{"phase":"edit","iteration":N}` before §4e, including when the adversary
or CI introduced the blockers. iteration N at the limit may finish review and
approve, but further edits require another review and return `MAX_ITERATIONS`.
earlier §4d and §4d.1 comparisons keep their existing precedence. the edit
check is the final boundary before changing files.

completion uses `phase:"completion"` with the just-completed iteration number;
its comment inputs and decisions are owned by [comment handling](comment-handling.md#success-gate-4d1).
a newly arrived comment cannot start another iteration at the cap.

phase calls require valid iteration counters. malformed input exits 2 and routes
to `SETUP_ERROR`. callers without `phase` retain the existing comparisons below.

## required reviews at completion

completion requires the last history entry to match `state.iteration`, with
equal nonempty `head_sha_before` and `head_sha_after`. `reviewers_completed`
must contain exactly the effective `approvers_required_list`, or the full panel
when that setting is absent. absent legacy receipts cannot establish completion.
receipt production is owned by [reviewer orchestration](reviewer-orchestration.md#completed-reviewer-responses).

any reviewer error, missing or invalid final adversary response, wrong adversary
identity, no-findings response without approval, shallow approval, or legacy
shallow give-up returns `REVIEW_INCOMPLETE`.
final adversary approval requires at least one nonblank `evidence.files_read`
entry. this completion requirement does not change the panel's shallow-review
classification or establish assigned-file coverage.
invalid required-panel configuration or an unreadable reviewer schema is a
`SETUP_ERROR`. incomplete reviews use §4i's no-commit record path and Step 5's
local report, without creating findings or entering the edit phase.

after the final CI wait and comment fetch, observe `current_head` and
`remote_head` immediately before invoking completion. both must equal the
reviewed head; a mismatch returns `EXTERNAL_PUSH`. missing observations or a
failed observation command are `SETUP_ERROR`. do not reuse iteration-entry SHAs.
the [completion invocation](comment-handling.md#success-gate-4d1) supplies these
inputs and then applies the existing comment gate.

## NO_PROGRESS

Compares the current blocker set against `history[-1]` and `history[-2]`, each **separately**.

- **Equal size plus a one-to-one pairing.** Containment scans are not enough in either direction:
  matching is neither transitive nor injective, so one current blocker can satisfy two previous ones
  (lines 10 and 20 are both within the window of 15) and a genuine shrink from two blockers to one
  would read as unchanged. Each current blocker must pair with a *distinct* previous one.
- **Two entries, never pooled.** An oscillation (a fix for A reintroduces B, whose fix reintroduces
  A) never repeats consecutively, so `history[-1]` alone would run to `MAX_ITERATIONS` pushing a
  commit per iteration. But pooling the two entries into one candidate set is also wrong: a current
  `{A,B}` would match a union of `{B}` and `{A}` and fire on a set that repeats neither iteration.
- **Promoted blockers count.** `promote_findings.py` appends a promoted suggestion to its
  `blockers[]` partition without rewriting `severity` (the one severity rewrite, the merge-layer
  adversary-blocker-over-nit override, lands with `severity: "blocker"` and matches the filter), so a `severity == "blocker"` filter alone
  drops every promoted blocker from the lookback and an unchanged one would never fire. The
  effective set is reconstructed from `addressed[]`, which records each promotion by file, line and
  summary.
- **Deferred blockers do not count.** `promote_findings.py` routes every `out_of_scope` finding to
  `deferred[]` whatever its severity, so one persisted with `severity: "blocker"` was never in the
  set the loop tried to fix. Counting it adds an entry the current set never has, so an unchanged
  in-scope set fails the equal-size check, and a finding's first in-scope appearance reads as a
  repeat.
- **The two sides are not the same kind of set.** What the caller passes is this iteration's
  synthesized panel blockers, which are **pre-adversary**: §4d evaluates `NO_PROGRESS` before §4d.0
  runs. What it is compared against is the **post-merge** set persisted in `history[].findings`:
  panel blockers plus any adversary endorsements, unmatched adversary findings, and
  blocker-over-nit overrides merged in by §4d.0/§4d.0.5, because §4i writes at iteration end. Don't "fix" the caller to pass a post-adversary set.

### how blockers are matched

`finding_matcher.is_match_or_summary`, which is the §4c dedupe rule (see
[`synthesis.md`](synthesis.md)) plus one fallback. Reviewers reword the same finding between runs, so
string equality lets a stuck loop keep going.

The fallback exists because `findings[]` makes `file` and `line` independently optional while §4c
handles their absence in two different and equally wrong ways: a missing `line` is rejected outright,
so a CI-derived blocker carrying `file` and no `line` never matches its own repeat; and two absent
`file` values compare *equal*, so unlocated findings would match on fuzzy overlap. When either side
is unlocated the comparison instead falls back to exact equality of normalized summaries
(lowercased, tokenized, stop-words dropped).

Four details in that fallback are load-bearing:

- absence is `is None`, not falsiness, so `line: 0` stays a location rather than becoming a
  summary-only comparison against something hundreds of lines away
- the §4c rule is tried **only** when both sides are located. `is_match` reads two absent `file`
  values as equal, so trying it first would let two unlocated findings with nearby lines match on
  fuzzy overlap instead of the exact summary equality this fallback is for
- a `file` named on **both** sides must agree, or the same summary in two different files reads as
  one repeated finding. One side omitting it is fine, which is the case the fallback is for
- a summary that normalizes to an empty token set never matches, mirroring `token_overlap`'s
  treatment of no-signal input

## CI_STUCK

Walks `history` backwards to the most recent entry that recorded any `ci_failed_checks`, and fires on
a **non-empty intersection** with this visit's names.

- **Not `history[-1]`.** §4d.1 runs only when the panel has nothing left to flag, so iterations in
  between persist `ci_status: "skipped"` and no names. Absent and `[]` mean the same thing.
- **Only `ci_status: "failure"` entries count.** §4i records names on a failure, so names riding on
  a success or skipped entry are stale or malformed. Honouring them would fire `CI_STUCK` spuriously
  and, when the stale names are disjoint, hide an older real failure behind them.
- **Not set equality.** `{build, lint}` followed by `{build}` is a stuck `build`; equality would read
  the departed `lint` as progress and keep looping.
- Only names are compared. Whether the commits in between "addressed" the failure is unanswerable in
  practice: the loop commits every iteration, so the answer is always yes and the exit would never
  fire.

See [`ci-conversion.md`](ci-conversion.md) for how `ci_wait.sh` exit codes map to statuses.

## When history is unusable

Missing, empty, or malformed `history[]` fires **neither** exit. Malformed means the whole entry, not
the bad item: dropping one unparseable finding or promotion record would leave a smaller set that a
current set could match exactly, firing `NO_PROGRESS` on a blocker set that genuinely shrank. An
unusable entry is skipped whole, and the other lookback entry is still consulted.

A persisted finding is usable only if it satisfies the schema's whole finding contract: `reviewer`,
`severity`, `scope`, `summary`, plus well-typed `file`/`line`. Checking a subset is not enough:
anything the severity filter reads but the check ignores gets dropped silently, which is the same
shrinking-set bug by another route. A missed `NO_PROGRESS` costs
iterations up to `max_iterations`, which is the backstop; a spurious one aborts a healthy run. That
is the opposite bias from `select_panel.py`, which fails open toward running the full panel, because
there the expensive mistake is skipping a persona that owns an open blocker.
