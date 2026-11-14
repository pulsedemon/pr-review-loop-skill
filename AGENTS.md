# PR Review Loop (Codex-compatible guidance)

This file provides Codex-specific routing for the PR Review Loop skill. The full contract
lives in `SKILL.md` — read it for the automation contract, inputs, workflow, exit statuses, and safety rails.

## When to invoke

User provides a PR reference (URL, `#123`, "the current branch's PR", or
similar) and asks to: auto-review, auto-fix, iterate on, babysit, drive to
merge, or ship the PR end-to-end. Also: handle reviewer feedback (including
bot reviewers like Copilot or CodeRabbit) and CI failures on a PR without
further approval.

## Required tools

- `gh` CLI (authenticated)
- `git`
- `jq`
- `sonar` CLI (SonarSource SonarQube CLI, authenticated via `sonar auth
  login`) — only if the repo uses SonarCloud/SonarQube in CI. Relevant
  subcommands:
  - `sonar list issues --project <key> --pull-request <N>`
  - `sonar list projects --query <name>`
  - `sonar api get "/api/qualitygates/project_status?projectKey=<key>&pullRequest=<N>"`
  - `sonar verify --file <path>`
  - `sonar auth status`

## Repo artifacts

- `SKILL.md` — full step-by-step workflow (authoritative)
- `reviewers/*.md` — reviewer persona prompts
- `reviewers/adversary.md` — adversarial second-pass reviewer
- `gates/pr-scope.md` — PR-scope gate persona prompt (Step 3.5)
- `docs/synthesis.md`, `docs/adversary.md`, `docs/resume.md`, `docs/ci-conversion.md`, `docs/skill-update.md`, `docs/model-overrides.md` — mechanics docs
- `scripts/` — helper scripts (fetch, validate, promote, metrics; run `sync_skill.sh` at the start of Step 1)
- `templates/state.schema.json`, `templates/summary_*.md`, `templates/commit_message.md`

## Codex-specific notes

1. **Parallel fan-out.** Launch each reviewer or delta-gate phase as one batch:
   one subagent call per reviewer or gate candidate, all inside a single
   message, and await results only after the last launch. When the host cannot
   spawn subagents in parallel, either fan-out may run sequentially,
   but those outputs must still stay independent until synthesis (reviewers) or
   validation/selection (delta-gate). For Codex, non-inherited model
   tiers map to `spawn_agent.model`.
2. **State file.** Maintain `<git-dir>/pr-loop/state.json`, where `<git-dir>` is `git rev-parse --git-dir` (never tracked); read before each iteration, write after.
3. **Scripts over re-implementation.** Prefer the helpers in `scripts/` over re-implementing logic (e.g., `write_iteration_metric.sh`, `write_terminal_metric.sh`).

See `SKILL.md` for everything else. See [`docs/editing-personas.md`](docs/editing-personas.md) for the persona manifest workflow and [evaluation guidance](docs/editing-personas.md#evaluating-reviewer-changes).
