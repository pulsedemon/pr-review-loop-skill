# pr-review-loop

A portable skill that runs a multi-agent GitHub PR review loop: reviews the diff with a panel of reviewer personas, plans fixes, commits, pushes, waits for CI, and repeats until all reviewers approve and CI is green (or a safety condition terminates the loop).

Installs into **Cursor**, **Claude Code**, **Codex**, and **opencode**. See [Validation scope](#validation-scope) for the evidence behind host support.

## At a glance

Point it at a GitHub PR and the loop reviews the diff with a panel of reviewer personas, plans in-scope fixes, commits, pushes, and waits for CI. It repeats until every required reviewer approves and CI is green, or a safety condition terminates it. Native permissions and higher-priority instructions apply throughout; the [automation contract](SKILL.md#automation-contract-read-this-first) defines when it continues or stops.

## What it does

The full step-by-step contract is in [`SKILL.md`](SKILL.md). Briefly: the loop iterates through review → plan → commit → push → CI wait, with parallel reviewer fan-out, an adversarial second-pass before approval, and a single summary comment on the PR at exit.

run reviewer personas (correctness, tests, security, performance, readability, yagni, requirements, comments, error_handling, type_design, blind_spots) in parallel against the diff, launched as one batch: one subagent call per reviewer, all inside a single message, and await results only after the last launch. on iterations `>= 2` with `delta_gate=true`, the delta-gate candidate fan-out follows the same recipe. when the host cannot spawn subagents in parallel, either fan-out may run sequentially; keep outputs independent until synthesis (reviewers) or validation/selection (delta-gate).

**Operates in-place in your current repo checkout.** Loop state lives in `<git-dir>/pr-loop/` (`git rev-parse --git-dir`, never tracked). **Never auto-merges.** Merge stays a human action. Read the [security policy](SECURITY.md) before running it on a repository.

## Requirements

See [Preconditions](SKILL.md#preconditions) for the required tools, authentication, and checkout state.

If your host's `python3` does not meet the Python requirement, use the [Python environment setup](#python-environment-if-needed). [CONTRIBUTING.md](CONTRIBUTING.md) covers development hooks and checks.

## Install

```bash
git clone https://github.com/pulsedemon/pr-review-loop-skill.git
cd pr-review-loop-skill
./install.sh --codex
```

Choose the flag for your host below, then restart that host. This repository is private, so cloning requires GitHub access. Run `gh auth login` if you have not authenticated yet.

Keep the cloned skill directory: installed links depend on it. The default checkout follows `main` through [startup sync](docs/skill-update.md#startup-sync). To keep a fixed revision instead, use [version pinning](docs/skill-update.md#pinning-a-version).

A bare `./install.sh` installs only into **detected** hosts, meaning hosts whose config dir already exists: `~/.cursor`, `~/.claude`, `${CODEX_HOME:-~/.codex}`, and `${XDG_CONFIG_HOME:-~/.config}/opencode`. An explicit host flag installs that host regardless of detection; `--force` alone skips detection and (re)installs into all four.

This installs the skill at:

| Host | Location | Method |
| ------ | ---------- | ------ |
| Cursor | `~/.cursor/skills/pr-review-loop/` | Hardlinked copy of skill files (`.git` and dev caches excluded; Cursor does not discover symlinked skill dirs) |
| Claude Code | `~/.claude/skills/pr-review-loop/` | Symlink |
| Codex | `~/.agents/skills/pr-review-loop/` and `$CODEX_HOME/skills/pr-review-loop/` (defaults to `~/.codex/skills/pr-review-loop/`) | Symlinks |
| opencode | `${XDG_CONFIG_HOME:-~/.config}/opencode/skills/pr-review-loop/` plus three `prl-*` tier agents in `${XDG_CONFIG_HOME:-~/.config}/opencode/agent/` | Symlinks |

When your checkout and `~/.cursor` are on the same filesystem, the Cursor install hardlinks skill files so edits to **existing** files stay in sync. New or removed **top-level** paths and legacy trees that included `.git` are picked up when you rerun `./install.sh` (or `./install.sh --cursor`), which refreshes the install when the layout drifts. If hardlinking is not possible (different volumes), the script falls back to a plain copy and prints a note: rerun install after large skill changes, or uninstall and reinstall to force a full resync. A `.pr-review-loop-source` marker records which checkout was installed.

To install into only one host:

```bash
./install.sh --cursor
./install.sh --claude
./install.sh --codex
./install.sh --opencode
```

For Claude Code, Codex, or opencode, rerun the host command with `--force` after moving the checkout to replace stale symlinks. Without it, conflicting links are reported and the install exits non-zero.

To uninstall:

```bash
./install.sh --uninstall
```

### Python environment (if needed)

Skip this if your host already has the Python environment required by the [preconditions](SKILL.md#preconditions). The installer places skill files; it does not install Python packages.

Otherwise, install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run these commands from the cloned skill directory:

```bash
uv sync --group dev --frozen
source .venv/bin/activate
```

This locked environment includes the runtime dependency and development tools. Start your host from this activated shell in the target PR checkout. In a new shell, activate the skill clone's environment again before starting the host.

### opencode setup

Install the skill and the tier agents with:

```bash
./install.sh --opencode
```

Restart opencode afterwards: it reads config, skills, and agents once at
startup, with no hot reload. The three `prl-*` agent files ship without a
`model` field, so every phase inherits the session model, exactly like
`inherit`, until you set `model: <provider>/<model-id>` in each installed
agent file under
`${XDG_CONFIG_HOME:-~/.config}/opencode/agent/` to activate tiered routing (see
[`docs/model-overrides.md`](docs/model-overrides.md)). The agent files are
symlinks into this checkout, so that edit keeps the clone dirty and pauses the
startup-sync fast-forward until you commit or revert it. opencode also
auto-loads skills from `~/.claude/skills`, so a Claude Code install is already
visible there; the native install keeps opencode working independently of it.

Note that opencode's `task` tool has no per-invocation model parameter, unlike
the other hosts: model tiers are realized through the installed agent
definitions, not through spawn-time arguments.

## Validation scope

Installer and update fixtures pass on macOS 27.0.1 for all four host layouts. These checks cover file placement, refresh, uninstall ownership, and update pinning; they do not start a host or prove that it completes a review.

| Host | Installer fixtures | Observed runtime evidence |
| --- | --- | --- |
| Cursor | Passed | Not verified |
| Claude Code | Passed | Not verified |
| Codex | Passed | [Live approval path](tests/scenarios/27-comment-reply-disposition.md#live-github-approval-path-2026-11-14) at `678b598`; [injected fixture branches](tests/scenarios/24-adversary-full-default.md#changed-default-fixture-run-2026-11-14) at `90e5593` |
| opencode | Passed | Not verified |

CI runs the helper checks on Ubuntu. Native Windows use is unverified. The [scenario manifest](tests/scenarios/manifest.yaml) distinguishes deterministic checks, historical manual observations, and behavior that remains a design fixture.

[Scenario 25](tests/scenarios/25-persona-recall-sharpening.md#observed-comparison-2026-11-14)
records actual Codex reviewer dispatch on bounded synthetic inputs. Its
incomplete comparison does not justify changing the default panel.

## Usage

In any supported host:

> Use the pr-review-loop skill on https://github.com/acme/api/pull/482

Variants:

- **Dry run (review only, no commits):** `Dry-run pr-review-loop on <PR URL>`
- **Subset of reviewers:** `Run pr-review-loop on <PR URL> with only security and tests reviewers`
- **Lower cap:** `Run pr-review-loop on <PR URL> with max_iterations=5`
- **Custom PR-scope threshold:** `Run pr-review-loop on <PR URL> with max_new_loc=800`
- **Force PR-scope gate on (testing):** `Run pr-review-loop on <PR URL> with pr_scope=true`
- **Disable PR-scope check:** `Run pr-review-loop on <PR URL> with pr_scope=false`
- **Cheapest model routing:** `Run pr-review-loop on <PR URL> with subagent_model_profile=cost_saver`
- **Pin every phase to the parent model:** `Run pr-review-loop on <PR URL> with subagent_model_profile=inherit`

## Loop statuses

<!--[[[cog
import _exit_statuses_for_cog as E
cog.outl("| Status | Meaning |")
cog.outl("| --- | --- |")
for status, description in E.statuses():
    cog.outl(f"| `{status}` | {description} |")
]]]-->
| Status | Meaning |
| --- | --- |
| `running` | Loop is mid-iteration; not a terminal exit. |
| `success` | required reviews complete on the unchanged head, zero blockers, CI green or no checks registered, and required comment handling complete. |
| `max_iterations` | reached the configured iteration cap. |
| `no_progress` | Same blockers came back within the last two iterations. |
| `tests_regressed` | Local tests regressed after an edit. |
| `ci_stuck` | Same CI check failing on two consecutive CI visits. |
| `external_push` | Remote head moved unexpectedly between iterations. |
| `scope_split_recommended` | PR exceeded the new-LOC threshold; user opted to abort so the work can be moved into smaller PRs. |
| `dry_run_complete` | dry_run=true: reviewers ran and synthesized, nothing was committed or pushed. |
| `setup_error` | Local tooling problem (missing CLI, malformed state, etc.); no PR comment posted. |
| `review_incomplete` | a required review or comment operation did not complete. report the failed operation locally; do not post a final pr comment. |
<!--[[[end]]]-->

`running` is the in-progress status; all other statuses are terminal. final output follows the [terminal-status routing](docs/step5-summary.md#terminal-status-routing).

These are the values of `state.json.status` (lowercase, sourced from `templates/state.schema.json`'s `status.enum`). [`SKILL.md`](SKILL.md) and a few helper scripts also refer to the corresponding terminal-exit labels in uppercase form (`SUCCESS`, `MAX_ITERATIONS`, `SETUP_ERROR`, …) for the procedural exit; both forms describe the same underlying enum.

## Safety rails

The hard-coded, non-overridable rails (no force-push, no amend, no `--no-verify`, no protected-branch pushes, no auto-merge, abort on external push, refuses dirty trees, refuses repo/origin mismatch) are enumerated in [`SKILL.md`](SKILL.md) under "Safety rails (non-negotiable)" (with `Preconditions` and §4h covering the runtime-enforced subset).

## Scope discipline

Reviewer personas are prompted with a strict scope rule: only flag as `blocker` things that are objectively wrong (correctness, security, test coverage) or that violate an explicit requirement in the PR body or linked ticket. Style preferences, "consistency with the pattern elsewhere", and inferred requirements are recorded as deferred questions for humans, not fixed automatically.

## Layout

```
pr-review-loop-skill/
├── SKILL.md                  # entrypoint for Cursor + Claude Code + opencode
├── AGENTS.md                 # Codex-compatible mirror
├── README.md
├── install.sh
├── hosts/
│   └── opencode/             # tier agent files linked into opencode's agent dir
├── reviewers/
│   ├── personas.yaml
│   ├── correctness.md
│   ├── tests.md
│   ├── security.md
│   ├── performance.md
│   ├── readability.md
│   ├── yagni.md
│   ├── requirements.md
│   ├── comments.md
│   ├── error_handling.md
│   ├── type_design.md
│   ├── blind_spots.md
│   ├── gate.schema.json
│   └── adversary.md
├── docs/
│   ├── change-map.md
│   ├── delta-gate.md           # canonical delta-gate mechanics for §4a.1
│   └── synthesis.md            # matcher/promotion mechanics
├── gates/
│   └── pr-scope.md             # optional PR-size gate (Step 3.5)
├── ci-integrations/
│   ├── README.md               # contract for converting CI failures → blockers
│   └── sonar.md                # SonarCloud / SonarQube integration
├── scripts/
│   ├── fetch_pr.sh
│   ├── state_init.sh
│   ├── safe_push.sh
│   ├── ci_wait.sh
│   ├── count_new_loc.sh        # added-LOC count, excluding lock/generated/snapshot files
│   ├── run_local_validation.sh # stack-aware local test/lint/typecheck (Step 4f)
│   ├── select_panel.py         # deterministic panel selection for delta-gated iterations
│   ├── validate_gate_output.py # validates one delta-gate output before selection
│   ├── validate_reviewer_output.py # validates reviewer subagent JSON (Step 4c)
│   ├── match_findings.py       # Jaccard matcher for finding dedupe (§4c)
│   ├── promote_findings.py     # partitions findings; owns all three promotion paths (§4c, §4d.0.5)
│   ├── fetch_sonar.sh          # Sonar issues → blockers (used by ci-integrations/sonar.md)
│   ├── fetch_sonar_gate.sh     # Sonar quality-gate failures → blockers
│   └── fetch_ci_log.sh         # generic CI log tail
├── templates/
│   ├── state.schema.json
│   └── commit_message.md
└── tests/
    ├── bats/                   # automated bats tests for scripts/
    ├── scenarios/              # manual pressure-test fixtures
    └── run.sh
```

## Extending

- **Add a reviewer persona:** edit `reviewers/personas.yaml`, run `scripts/regen.sh`, add or remove the matching `reviewers/<name>.md` file as needed, then run `bash tests/run.sh`. See `docs/editing-personas.md` for the full manifest-driven workflow.
- **Add a CI integration:** copy `ci-integrations/sonar.md` as a template, replace the name pattern and fetch logic, reference it from `ci-integrations/README.md`.
- **Change safety rails:** edit `scripts/safe_push.sh` (protected-branch list is at the top).
- **Change CI timeout:** second arg to `scripts/ci_wait.sh` (default 1800s).
- **Change iteration cap default:** fourth arg to `scripts/state_init.sh` (default 15) or invoke with `max_iterations=N` in the user prompt.
- **Change PR-scope exclusions:** edit the `is_excluded` case block at the top of `scripts/count_new_loc.sh`.
- **Add a local-validation stack:** add a new branch to `scripts/run_local_validation.sh` matching the new stack's lockfile/manifest.

## License

[MIT](LICENSE).
