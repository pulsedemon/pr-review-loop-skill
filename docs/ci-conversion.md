# CI failures → blockers (SKILL.md §4d.2): Mechanics

This document owns the `ci_wait.sh` exit mapping and the conversion rules that
[`SKILL.md`](../SKILL.md) §4d.1 and §4d.2 invoke.

## `ci_wait.sh` exit codes (§4d.1)

`scripts/ci_wait.sh` is the only CI wait in the loop; §4d.1 runs it after the
reviewer panel approves. Map its exit code as follows:

| Exit | Meaning | §4d.1 action |
| --- | --- | --- |
| 0 | all checks passed (or only skipped) | when §4e has required fixes pending (`SKILL.md` §4d.1), continue through §4e's budget check; otherwise append the §4i approval history entry (`ci_status: "success"`), then run the [comment completion gate](comment-handling.md#success-gate-4d1); only its complete result permits `SUCCESS` → Step 5 |
| 1 | at least one check failed/cancelled | convert each failed check to a blocker (see below), merge into the blocker list, record the failed check names in this iteration's `ci_failed_checks`, continue to §4e |
| 2 | timed out waiting for checks to conclude | exit `CI_STUCK` → Step 5 |
| 3 | usage error / not a git repo and no `--repo` | exit `SETUP_ERROR` → Step 5 (orchestrator invoked the helper wrong) |
| 4 | no checks ever registered (5 empty polls) | when §4e has required fixes pending (`SKILL.md` §4d.1), continue through §4e's budget check; otherwise nothing gates the merge and reviewers already approved: append the §4i approval history entry with `ci_status: "skipped"`, then run the [comment completion gate](comment-handling.md#success-gate-4d1); only its complete result permits `SUCCESS` → Step 5 |
| 5 | `gh` call failed (non-empty stderr) | exit `CI_STUCK` → Step 5 (CI status indeterminate) |

This is distinct from the fetch helper exit convention below, which governs
the §4d.2 blocker conversion.

## `CI_STUCK` on a repeatedly-failing check

§4d.1 exits `CI_STUCK` when two consecutive visits see the same check **name**
fail. The comparison is a non-empty intersection of this visit's failed check
names with those of the **most recent earlier entry that recorded any**, not
`history[-1]`: §4d.1 runs only when the panel has nothing left to flag, so any
iteration in between persists `ci_status: "skipped"` with no `ci_failed_checks`,
and comparing against it would intersect with nothing and never fire. One name in
common is enough. Not set equality: `{build, lint}` followed by `{build}` is a
stuck `build`, and equality would read the departed `lint` as progress and keep
looping. Do not ask whether the commits in between addressed the failure: the
loop commits once per iteration by construction, so that question always answers
"yes" and the exit never fires.

`ci_failed_checks` is the persisted record because
`<git-dir>/pr-loop/last_ci_status.json` is overwritten on every `ci_wait.sh` call and
cannot describe the previous visit.

## Conversion procedure

For each failed check from `ci_wait.sh`:

1. **Match an integration.** Look up `ci-integrations/` for a file whose
   name pattern matches the check's name (see `ci-integrations/README.md`).
   Existing integrations: `ci-integrations/sonar.md`. If matched, follow
   that integration's blocker-mapping and fallback rules. Do not apply
   the fallback below.

2. **Fallback (no integration matched).** Create one blocker per failed
   check, calling `scripts/fetch_ci_log.sh <pr_number> <check_name>` for
   context:

   ```json
   {
     "reviewer": "ci",
     "severity": "blocker",
     "scope": "in_scope",
     "summary": "<check_name> failed",
     "detail": "<last ~50 lines of job log>"
   }
   ```

## Fetch helper exit convention

The CI-conversion fetch helpers (`scripts/fetch_ci_log.sh`,
`scripts/fetch_sonar.sh`, `scripts/fetch_sonar_gate.sh`) reserve **exit 1** for
a usage error or missing `jq`. Map it to terminal `SETUP_ERROR` → Step 5. Never
retry it and never degrade it to a coarse blocker. Each helper's header lists
its other exits; the matched integration owns their recovery, and the next
section owns it for `fetch_ci_log.sh`.

Other helpers under `scripts/` keep their own exit codes in their headers, and
each call site maps them.

## `fetch_ci_log.sh` non-fatal exits

Other non-zero exits from `fetch_ci_log.sh` fall through to:

- **Exit 2** (`gh` missing): emit the blocker with
  `detail: "<check_name> failed; gh CLI unavailable, log context could not be fetched."`.
  If the same check fails again next iteration with no new code addressing
  it, let `NO_PROGRESS` surface it.
- **Exit 3, 4, 5**: emit the blocker with
  `detail: "<check_name> failed; log unavailable (fetch_ci_log.sh exit <N>: <stderr one-liner>)."`.

Never retry more than once. Never stop to ask the user.
