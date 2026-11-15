# Scenario 30: Tests coverage calibration

**Type:** Manual comparison of tests persona revisions using isolated PR fixtures.

## Setup

Freeze the old and revised persona with `SKILL.md`, `reviewers/`, `docs/`,
`templates/`, and `scripts/` in a scratch directory outside the checkout.
Export the tracked files of each fixture below into its own Git repository with
an empty base commit and one head commit. Keep expected dispositions outside
reviewer context.

| Case | Fixture | Expected revised response |
| --- | --- | --- |
| T | `reviewer-quality/case-03` as shipped | No `greeting` blocker or suggestion. |
| C | `reviewer-quality/case-04` as shipped | No blocker; no `greeting` suggestion. |
| P1 | case-04 without the missing-checker run and its two assertions in `checks.py` | Coverage blocker naming the exit-2 contract; no `greeting` blocker or suggestion. |
| P2 | case-04 with the exit assertion weakened to `in (0, 2)` under a comment stating exit 2 | Blocker: the assertion accepts exit 0; no `greeting` blocker or suggestion. |
| P3 | case-04 with a README sentence requiring `greeting(name)` to return `Hello, <name>` | Coverage blocker naming that contract. |
| P4 | case-04 with a documented `main.py` that prints `greeting("world")` | Coverage blocker naming the printed result. |
| P5 | case-04 with `[project]` and `py-modules = ["app"]` in `pyproject.toml` | Coverage blocker on the published `greeting`. |

T and C reproduce the recorded low-value blocker from
[scenario 25](25-persona-recall-sharpening.md#observed-comparison-2026-11-14).
P1 and P2 cover a real untested regression and an assertion that does not test
its claim. P3 to P5 check that specified, reached, and published code keeps its
blocker.

Check fixture behavior before dispatch. `python3 -B checks.py` fails only for T.
Changing `exit 2` to `exit 0` fails C and passes P1 and P2. Repository-pinned
Ruff passes all seven. P3's `greeting("Ada")` returns `Hello, Ada`, P4's
`main.py` prints `Hello, world`, and a P5 source build contains `app.py`. Only
P4 calls `greeting`, and every fixture checkout stays clean after the checks.

## Comparison procedure

Run the whole baseline arm before editing the persona, then the revised arm:
one fresh tests reviewer per case and revision, fourteen responses total. Keep
the model, effort, fixture bytes, permissions, and dispatch text constant.
Supply only the case's PR metadata, diff, source, persona, addenda, and schema,
with no path into the live checkout.

Validate each response with `scripts/validate_reviewer_output.py <response.json> --reviewer tests`.
Check native traces for reads of the checkout or the installed skill links; a
read there invalidates the cell. Label findings with the
[labeling protocol](../../tools/recall-harness/label.md). Count a blocker as
unsupported when its stated harm ties to no behavior a caller, user, or stated
contract depends on.

## Pass criteria

All seven revised responses meet the table and pass schema validation, with no
unsupported blocker. A seeded defect mentioned only as a suggestion does not
count as retained. T's seed (exit 0 when Ruff is missing) is a code defect
rather than a coverage gap; it is compared against the baseline, not required
by this change.

## Observed comparison, 2026-11-14

Fourteen fresh Codex `gpt-6.1-sol` sessions at high effort, read-only, with MCP
disabled, completed the comparison on a Witch-supplied route. No trace read the
checkout or the installed skill links.

The baseline was `reviewers/tests.md` at
`8742bb7e772b9dfcf8fbaa1f468dd65ac3151920`, SHA-256
`800f84e6a2e8098cc328ce4ae255644112f4f39b6a916c0856a2547b2986c8ee`.
The revised prompt's SHA-256 was
`2722a4e8804733500604dd96ab6ef53e430c0e166593a9b243fa4717199c5af5`.
Addenda and schema hashes were identical across arms.

| Case | Baseline | Revised |
| --- | --- | --- |
| T | Seed blocker; `greeting` blocker | Seed blocker |
| C | `greeting` blocker | `greeting` nit |
| P1 | Exit-2 coverage blocker; `greeting` blocker | Exit-2 coverage blocker; `greeting` nit |
| P2 | Weak-assertion blocker; `greeting` blocker | Weak-assertion blocker; `greeting` nit |
| P3 | Contract coverage blocker | Contract coverage blocker |
| P4 | Coverage blocker | Entry-point coverage blocker |
| P5 | Coverage blocker | Published-API coverage blocker |

Baseline: six useful findings, four low-value, zero false, four unsupported
blockers. Revised: six useful, three low-value, zero false, zero unsupported
blockers. All fourteen responses passed schema validation.

Limits: one sample per cell, tests persona alone, no panel, adversary, or other
host. The adversary can still raise a coverage blocker
(`reviewers/adversary.md`), which this run cannot observe. The judge knew each
arm, so judging was not blinded. The file-role wording was written from T and
C, so those cases are not held out, and no multi-statement trivial addition was
evaluated. Read-only sessions could not run mutation probes, so P2's blocker
rests on static reasoning. Raw responses, traces, fixtures, prompts, hashes,
and judgments are retained locally in ignored
`docs/superpowers/reviews/2026-11-14-tests-coverage-calibration/`.

_Validated with Codex `gpt-6.1-sol`, high effort, on the prompt hashes above: PASS._

## Validation status

**Status:** `manual_validated`
**Evidence:** The dated comparison above records all seven baseline and revised responses on frozen inputs.
