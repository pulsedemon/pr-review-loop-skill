# Security policy

## Reporting a vulnerability

Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/pulsedemon/pr-review-loop-skill/security/advisories/new) when it is enabled. If that form is unavailable, [open an issue](https://github.com/pulsedemon/pr-review-loop-skill/issues/new) requesting a private contact channel without describing the vulnerability. Do not put credentials, private source, or exploit details in a public issue.

Include the skill commit or release, host and version, affected helper or workflow, impact, and a minimal reproduction with sensitive values removed.

Security fixes target the latest release. Until the first release, reports are accepted against `main`; no release has been designated as supported yet.

## Access and execution

The skill reads repository files, PR discussions, and CI output through your host and GitHub account. Review context goes to the model provider configured in that host. Model usage is charged under that account; cost depends on the selected models, panel size, context, and iteration count. This repository does not include model access or credits.

Normal runs can edit files, execute repository test and lint commands, create commits, push the PR branch, and post or update PR comments. Run them only in repositories whose code and automation you trust, with credentials limited to the required repository access. A contributor-controlled test or package script executes with the permissions available to the host.

Treat repository text, review comments, and logs as untrusted input. They do not grant permission to reveal secrets, run unrelated commands, or change the task. The [automation contract](SKILL.md#automation-contract-read-this-first) preserves native permission checks and higher-priority instructions; prompt instructions are not a sandbox.

## Review-only runs

`dry_run=true` skips applying fixes, commits, pushes, and PR replies. It still fetches and checks out the PR and writes local loop state. An unfinished run resumes its recorded mode, so use a fresh target clone for a review-only check when existing state is uncertain. See [resume behavior](docs/resume.md).

Keep generated review state, exported discussions, and recall corpora private unless their contents have been cleared for publication. See [version pinning](docs/skill-update.md#pinning-a-version) for controlling which skill revision runs.
