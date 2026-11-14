# Scenario 11 — `count_new_loc.sh` stream separation

**Pressure type:** machine-readable contract / no parser breakage

## Setup

A test repo with the following diff against `main`:

- `src/app.ts` — 120 added, 5 deleted
- `src/app.test.ts` — 60 added, 0 deleted
- `node_modules/foo/index.js` — 200 added, 0 deleted (should be excluded by directory rule)
- `assets/logo.png` — binary diff (numstat emits `-` for both columns)
- `pnpm-lock.yaml` — 4,000 added, 100 deleted (lockfile exclusion)

The harness runs:

```bash
bash scripts/count_new_loc.sh main
```

…and captures stdout and stderr separately.

## Baseline behavior (no skill)

Not applicable — this scenario asserts the script's machine-readable contract directly. There is no "without skill" comparator; the script either upholds the contract or it doesn't.

## With skill (target behavior)

### stdout (exact shape)

- Line 1: a single integer (no whitespace, no prefix), equal to the sum of `added` columns for INCLUDED files. For this fixture: `180`.
- Lines 2+: TSV rows `<added>\t<deleted>\t<path>`, one per INCLUDED file, in `git diff --numstat` order. For this fixture, exactly two rows:
  - `120\t5\tsrc/app.ts`
  - `60\t0\tsrc/app.test.ts`
- No other lines on stdout. No trailing comment lines, no blank lines except the final newline after the last TSV row.

### stderr (diagnostic only)

- One line per excluded file. For this fixture, exactly three lines:
  - `# excluded: node_modules/foo/index.js`
  - `# excluded (binary): assets/logo.png`
  - `# excluded: pnpm-lock.yaml`
- Every stderr line starts with `# excluded:` or `# excluded (binary):`. No other prefixes. No raw error spew on the happy path.

### Cross-stream invariants

- `bash scripts/count_new_loc.sh main 2>/dev/null` emits **only** the integer + TSV rows (no `# excluded:` lines on stdout).
- `bash scripts/count_new_loc.sh main 2>&1 >/dev/null` emits **only** `# excluded:` / `# excluded (binary):` lines (no integer, no TSV).
- Exit code is `0`.

### Rename handling sub-case

If the diff includes a renamed file (e.g. `src/old.ts => src/new.ts`, 10 added 0 deleted), the TSV row MUST emit the post-rename path (`src/new.ts`) and the exclusion logic MUST apply to the post-rename path. A rename of a lockfile (`old-lock.json => package-lock.json`) MUST be excluded.

## Pass/fail criteria

- **Pass:** All of the above contract clauses hold for the fixture diff, AND the rename handling sub-case passes for both a regular rename and a lockfile rename.
- **Fail:** Any of:
  - stdout line 1 is not a bare integer.
  - stdout contains an `# excluded:` line.
  - stderr contains an integer line or a TSV row.
  - A rename emits a TSV row with the `old => new` form or with `{old => new}/suffix`.
  - A lockfile rename is included in the count.

## Validation status

**Status:** `ci_trusted`
**Proof sources:** `tests/bats/count_new_loc.bats`
