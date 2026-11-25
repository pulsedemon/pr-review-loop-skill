# CI integrations

A CI integration tells the loop how to convert one CI provider's failure into a structured blocker for §4e. Each integration is a markdown file in this directory plus optional fetch scripts in `scripts/`.

The loop picks an integration by matching the failed check's name against each integration's name pattern in order. If nothing matches, the [generic fallback](../docs/ci-conversion.md#conversion-procedure) applies (one blocker per failed check, with `scripts/fetch_ci_log.sh` for log context).

## Integration contract

Each `ci-integrations/<name>.md` must document:

1. **Name pattern**: a substring or regex that matches the failing check's `name` (from `gh pr checks`). Be specific enough not to swallow unrelated checks.
2. **Fetch step(s)**: the helper script(s) in `scripts/` (or inline `gh`/CLI calls) that pull structured failure data for the check.
3. **Blocker mapping**: how each piece of fetched data becomes one finding in the synthesizer's blocker list. The shape must satisfy `history.findings[]` in `templates/state.schema.json` (the schema CI blockers are persisted under): `severity: "blocker"`, `scope: "in_scope"`, and a non-empty `summary`. Use `reviewer: "ci/<name>"` so the source is traceable in state; `file`/`line`/`detail` are optional for PR-level gate failures. CI blockers do NOT need to satisfy `reviewers/output.schema.json`, which is scoped to reviewer-persona output (enum-restricted `reviewer`, conditional `file`/`line`/`detail`).
4. **Exit-code fallback**: what to do when a fetch script exits non-zero. Exit 1 follows the [fetch helper exit convention](../docs/ci-conversion.md#fetch-helper-exit-convention). Give every other exit a recovery, usually a coarse blocker built from `fetch_ci_log.sh`'s output that the next iteration's edits address. Never stop to ask the user.
5. **Optional local verification**: any CLI command an agent can run before pushing to predict whether a fix resolves the issue. Advisory only; CI is ground truth.

## Scope rule does not apply to CI blockers

Even if a CI failure looks like "consistency with a pattern elsewhere" or would otherwise be `out_of_scope` for a reviewer persona, it is in-scope here because CI gates the merge.

## Existing integrations

| File | Name pattern |
| --- | --- |
| [`sonar.md`](sonar.md) | check name contains `sonar`, `SonarCloud`, `SonarQube`, or `Quality Gate` |

To add a new one, copy `sonar.md` as a template, replace the name-pattern and fetch logic, and reference it from this README.
