# Skill install auto-update (startup sync)

## Pinning a version

A detached checkout keeps an installed revision fixed. From the skill clone, fetch tags and check out a published tag or a reviewed commit SHA:

```bash
git fetch origin --tags
git checkout --detach origin/main
git rev-parse HEAD
export PR_REVIEW_LOOP_SKIP_SKILL_SYNC=1
```

No release tag is published yet. The example pins the fetched main revision; record its SHA. Substitute a reviewed SHA or, once available, a published release tag to select that exact version. Set the environment variable in the shell that launches the host. Detached HEAD also makes the startup helper skip updates; the variable makes that choice explicit if the clone is later put on a branch.

To update, check out the selected new tag or SHA, run `uv sync --group dev --frozen`, refresh the installation for your host, and restart the host. Cursor refresh and opencode restart details are below. To follow a branch again, switch to it and unset `PR_REVIEW_LOOP_SKIP_SKILL_SYNC`; startup sync then follows the contract below. Do not discard local changes to change versions.

## Startup sync

On every loop invocation, the orchestrator runs `scripts/sync_skill.sh` **at the
start of Step 1**, before touching the user's PR checkout. The script fast-forwards
the **skill install directory** (the git clone that `install.sh` symlinks into
`~/.cursor/skills/pr-review-loop`, etc.), not the target repo.

## Contract

- **Best-effort:** sync failures never produce `SETUP_ERROR` and never block
  the PR loop. The run continues with whatever skill version is already on disk.
- **Fast-forward only:** uses `git fetch origin` and `git pull --ff-only`.
  Diverged local branches are left unchanged (pull fails with a stderr warning).
- **stderr prefix:** all messages use `sync_skill:` for easy filtering.

## Skip conditions

| Condition | Behavior |
| --- | --- |
| `PR_REVIEW_LOOP_SKIP_SKILL_SYNC=1` | Skip (offline runs, skill CI, local dev) |
| Skill root is not the physical Git top-level | Skip (copy install, including one inside an unrelated Git repository) |
| `git status --porcelain` non-empty | Skip pull (protects local skill development) |
| Detached `HEAD` | Skip |
| No `origin` remote | Skip |
| `git fetch` or `git pull --ff-only` fails | Warn; continue with installed version |

## Symlink installs

`install.sh` symlinks the host skill path to this repo. The script resolves
`SKILL_ROOT` from `BASH_SOURCE` (`scripts/..`), so it updates the real clone
regardless of which symlink path invoked it.

## opencode restart semantics

The opencode install is symlinked (skill dir and each `prl-*` agent file), so
`sync_skill.sh` fast-forwarding the clone keeps the on-disk content current,
but opencode reads config, skills, and agents once at startup and never
hot-reloads. A running opencode session keeps using the previously loaded
skill version until it is restarted. Same rule after editing an agent file:
restart to reload it.

## Hardlink (Cursor) installs

Claude/Codex symlink hosts see updates immediately (opencode's symlink content
is current too, but the running session reloads only after restart: see
"opencode restart semantics"). The Cursor install is a hardlinked
tree, so an update that *replaces* files (most `git pull`s) breaks those
hardlinks and leaves the install serving stale content. Re-running
`install.sh` detects this: it compares the installed tree against the source
(recursive paths + per-file content/inode) and rebuilds when anything diverged
so a stale Cursor install is fixed by `./install.sh` (or `--force` to rebuild
unconditionally). `sync_skill.sh` only fast-forwards the clone; it does not
re-run the installer.

## Resume and version changes

Sync runs on **fresh starts and mid-loop resumes**. Pulling mid-resume can
change persona prompts or synthesis behavior while `<git-dir>/pr-loop/state.json`
was written by an older skill version. That is an intentional tradeoff for
staying current. If behavior diverges unexpectedly, delete
`<git-dir>/pr-loop/state.json` and restart the loop.

## Contributors

If you have uncommitted changes in this skill repo, sync skips automatically.
Set `PR_REVIEW_LOOP_SKIP_SKILL_SYNC=1` to disable sync even on a clean tree.
