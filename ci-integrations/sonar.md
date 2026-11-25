# Sonar (SonarCloud / SonarQube)

Converts failed Sonar checks into blockers for the PR review loop. Follows the contract in [README.md](README.md).

## Name pattern

A failed check matches if its name (from `gh pr checks`) contains any of: `sonar`, `SonarCloud`, `SonarQube`, `Quality Gate`.

## Fetch steps

Sonar failures have two independent sources: individual **issues** (per file/line) and **quality-gate conditions** (PR-level aggregates like new-code duplication or coverage %). Fetch both.

### 1. Individual issues

```bash
bash "$SKILL_ROOT/scripts/fetch_sonar.sh" <pr_number>
```

Returns a JSON array. Each element looks like (non-exhaustive):

```json
{
  "key": "AZ22...",
  "rule": "typescript:S3776",
  "severity": "CRITICAL",
  "component": "apps/web/server/middleware/10-catalog-preview-auto.ts",
  "line": 174,
  "message": "Refactor this function to reduce its Cognitive Complexity from 16 to the 15 allowed.",
  "type": "CODE_SMELL",
  "impacts": [{ "softwareQuality": "MAINTAINABILITY", "severity": "HIGH" }],
  "effort": "6min",
  "tags": ["brain-overload"]
}
```

Map each issue to a blocker:

```json
{
  "reviewer": "ci/sonar",
  "severity": "blocker",
  "scope": "in_scope",
  "file": "<issue.component>",
  "line": <issue.line>,
  "summary": "<issue.rule>: <issue.message>",
  "detail": "Sonar <issue.type> severity=<issue.severity>. Rule: <issue.rule>. Impact: <first impact softwareQuality>=<first impact severity>. Effort: <issue.effort>."
}
```

### 2. Failing quality-gate conditions

```bash
bash "$SKILL_ROOT/scripts/fetch_sonar_gate.sh" <pr_number>
```

Returns a JSON array of failing conditions:

```json
{
  "metricKey": "new_duplicated_lines_density",
  "status": "ERROR",
  "actualValue": "22.8",
  "errorThreshold": "3",
  "comparator": "GT"
}
```

Map each condition to a PR-level blocker (no file/line):

```json
{
  "reviewer": "ci/sonar-gate",
  "severity": "blocker",
  "scope": "in_scope",
  "summary": "Quality gate: <metricKey> <actualValue> <comparator> <errorThreshold>",
  "detail": "Sonar gate condition '<metricKey>' failed. Actual: <actualValue>. Threshold: <comparator> <errorThreshold>. Fix requires reducing the metric on changed code (e.g. extract duplicated logic, add tests for new-code coverage, fix new violations)."
}
```

Common `metricKey` values:

| metricKey | Fix strategy |
| --- | --- |
| `new_duplicated_lines_density` | Extract duplicated logic; generate one copy from the other (codegen); move to a shared module |
| `new_violations` | Resolve with `fetch_sonar.sh` issues |
| `new_coverage` | Add tests covering the changed code |
| `new_security_hotspots_reviewed` | Review and resolve hotspots via Sonar UI or `sonar api` |
| `new_security_rating` / `new_reliability_rating` / `new_maintainability_rating` | Usually resolves when underlying issues are fixed |

## Local verification (optional)

Before pushing, the agent may run `sonar verify --file <path>` on edited files to check whether a fix is likely to resolve the issue:

```bash
sonar verify --file apps/web/server/middleware/10-catalog-preview-auto.ts
```

Advisory only. CI remains ground truth.

## Raw API escape hatch

For any Sonar data not covered above:

```bash
sonar api get "/api/<endpoint>"
```

Example: duplications for a specific file in a PR:

```bash
sonar api get "/api/duplications/show?key=<project_key>:<path>&pullRequest=<pr_number>"
```

## Exit-code fallbacks

Exit 1 follows the [fetch helper exit convention](../docs/ci-conversion.md#fetch-helper-exit-convention). For the other exits of `fetch_sonar.sh` / `fetch_sonar_gate.sh`:

- **Exit 2** (CLI missing): emit a single coarse blocker summarizing the CI failure from `bash "$SKILL_ROOT/scripts/fetch_ci_log.sh" <pr_number> <check_name>` and continue.
- **Exit 3** (not authenticated): same, emit coarse blocker, continue. Note the auth issue in `detail`.
- **Exit 4** (project key ambiguous): re-run passing the project key explicitly. Discover candidates via `sonar list projects --query <repo_name>`.
- **Exit 5** (API error): retry once, then fall back to coarse blocker.

Never stop to ask the user.
