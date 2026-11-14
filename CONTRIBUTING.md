# Developing on pr-review-loop

## Issues and pull requests

For a bug report, include the skill commit or release, host and version, operating system, command or invocation, expected result, and a minimal reproduction. Remove credentials and private repository content. Follow [SECURITY.md](SECURITY.md) for vulnerabilities.

Fork the repository, create a branch, and open a PR against `main`. Explain the behavior changed and how you verified it. Contributor forks are welcome; the skill's [automated push path](SKILL.md#preconditions) supports branches in the PR repository, so it cannot push fixes to a contributor's fork.

Contributions are licensed under the repository's [MIT license](LICENSE). Submit only work you have authority to contribute, and retain required attribution.

## Editing the skill

This repo *is* a skill. Edits to `SKILL.md`, `reviewers/*.md`, `docs/*.md`,
and `templates/*.md` change runtime behavior the same way a code change
would: a host LLM reads them as instructions. Before editing, see
[`docs/change-map.md`](docs/change-map.md) for the source of truth, dependent
surfaces, and validation command for each common edit, and `CLAUDE.md` for
the architecture.

The change map and the rest of `docs/` refer to the test suite as
`bash tests/run.sh`. The `uv run` prefix shown below is only needed to use
the uv-managed toolchain; both forms run the same suite.

## One-time setup

Create the [locked Python environment](README.md#python-environment-if-needed), even if your host already meets the runtime requirements, then install git hooks:

    uv run pre-commit install

After this, every `git commit` runs the pre-commit hook stack on staged files.

## Running checks manually

Run all pre-commit hooks against every file:

    uv run pre-commit run --all-files

Run the bats test suite:

    uv run bash tests/run.sh

Skip a hook for a single commit (use sparingly):

    SKIP=ruff git commit -m "..."

## Updating tool versions

Bump a Python dep:

    uv lock --upgrade-package <name>
    uv sync --group dev
    git add uv.lock && git commit -m "build: bump <name>"

Bump pre-commit hook versions:

    uv run pre-commit autoupdate

If you bump ruff in `.pre-commit-config.yaml`, also run `uv lock --upgrade-package ruff`
so the uv-managed ruff (used by CI) matches the pre-commit pin. Same for yamllint:
`uv lock --upgrade-package yamllint` after bumping its `rev:`.

If you bump actionlint in `.pre-commit-config.yaml`, also update the `version:` pin
in the `actionlint` job in `.github/workflows/ci.yml`.

If you bump shfmt in `.pre-commit-config.yaml`, also update `SHFMT_VERSION` in the
`shfmt` job in `.github/workflows/ci.yml`.

## Policy

CI (`.github/workflows/ci.yml`) is the authoritative gate. Pre-commit is the fast
local mirror: if a hook passes locally but CI fails, CI wins, fix the discrepancy.
