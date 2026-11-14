# Working tree addendum

Shared by every reviewer, including the adversary. Each reviewer file links here from its own `## Working tree` section.

You share one checkout with the other reviewers running in parallel and with the orchestrator, which edits files in the same tree while you read. The skill operates in place by design and does not create a worktree.

**Never run `git checkout`, `git stash`, `git restore`, `git reset`, or `git clean` in this repo.** A dirty tree during a run is far more likely to be the orchestrator mid-edit than stale drift. Reverting it destroys work in progress, and the loss is silent. A leftover or reverted change also trips the Step 3.6 working-tree guard on the next resume, which aborts the run.

**Do not modify anything inside this checkout.** No `Edit`, no `Write`, no redirect into the tree, no `sed -i`, tracked or untracked. You are reading, not fixing. An untracked file you leave behind is as damaging as an edit: the Step 3.6 guard reads `git status --porcelain`, which counts untracked paths too.

If you need to write scratch output, write it outside the repo, under a `mktemp -d` directory. Return your findings as JSON in your result, not as a file.

Mutation testing stays expected where your persona calls for it. Do it on a copy, never in place. You receive the head SHA; write the copy outside the repo and mutate that:

```bash
scratch=$(mktemp -d)
git show <head_sha>:<path> > "$scratch/<basename>"
```

If `git status --porcelain` is non-empty, do not clean it and do not assume the change belongs to the PR. Before reporting a finding, check every modified file the finding rests on, not just the one you are anchoring it to. Your procedure sends you into callers, tests, and consumers outside the diff, so a finding anchored to a clean line can still be resting on a dirty one. Re-read each with `git show <head_sha>:<path>` and confirm the finding holds against that content alone. Uncommitted bytes are not this PR.

Report what you cannot do rather than working around it. A reviewer that reverts a file to get a clean read has cost more than the finding was worth.
