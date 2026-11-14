**Recommended split** (move the listed files into the named sub-PRs):

- **<split name>** — <rationale> (~<estimated_new_loc> new LOC)
  - <file/path/one>
  - <file/path/two>
- **<split name>** — <rationale> (~<estimated_new_loc> new LOC)
  - <file/path/three>

**Stays in this PR after the split:**

- <file/path/remaining-1>
- <file/path/remaining-2>

> Move these files into the new PRs — do not re-create them. After each new PR is open, remove the moved files from this branch so this PR shrinks to the residual set above.
