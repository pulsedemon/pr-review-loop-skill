# Manifest-driven generators

This doc captures the **generator convention** used to keep manifest-derived
surfaces in sync. The first instance is `reviewers/personas.yaml` driving the
SKILL.md "Reviewer personas" bullet list and the `reviewer.enum` in
`reviewers/output.schema.json` (see [`editing-personas.md`](editing-personas.md)
for that specific workflow). This doc is for **adding new generated surfaces**
later, so they all behave the same way.

## Why this exists

The repo's editing rule is "manifest is source of truth; everything else syncs
to it." A hand-written sync test per surface lets an editor "fix" the wrong
end of the comparison. A generator rewrites every dependent surface from the
manifest with one command, and CI runs it in check mode, so drift cannot be
committed.

## Format → tool

| Comment syntax in target file | Generator tool | Why |
| --- | --- | --- |
| HTML comments (`<!-- -->`): Markdown, HTML, XML | [cog](https://nedbatchelder.com/code/cog/) with `<!--[[[cog ... ]]]-->` markers | cog ships HTML-comment-style markers as the default; edits in place with `-r`. |
| Hash comments (`#`): YAML, shell, Python, TOML | cog with `# [[[cog ... ]]]` markers | Same `-r` flow; just swap the marker style. |
| No comments: JSON, most lockfiles | Standalone Python script following [`scripts/regen_adversary_caps.py`](../scripts/regen_adversary_caps.py)'s shape | No marker possible. Splice via parser-validated regex. |

Cog is the default; reach for a standalone script only when the target format
has no comment syntax at all.

## Contract every generator must honor

These rules apply equally to cog-managed regions and standalone scripts.

1. **Two modes.** `--check` (validates, exits non-zero on drift) and `--write`
   (rewrites in place). [`scripts/regen.sh`](../scripts/regen.sh) runs cog
   and every generator with `--write`, or with `--check` when it is given
   `--check`; [`scripts/regen-check.sh`](../scripts/regen-check.sh) is the CI
   entrypoint for `regen.sh --check`.
2. **Exit codes.** `0` ok, `3` manifest error or a target the generator
   cannot read or find its region in, `5` drift detected
   (`generator_io.MANIFEST_ERROR_EXIT`, `generator_io.DRIFT_EXIT`).
   `regen_panel_counts.py` exits `5` for malformed region markers, and its
   `--validate-markers` and `--validate-coverage` modes exit `5` for any
   failure, an unreadable file included. cog also exits `5` on drift, so
   `regen.sh --check` passes every status through unchanged.
3. **Drift output.** On drift, emit a unified diff to stderr and a literal
   fix hint: `Run scripts/regen.sh to regenerate ...`. The literal
   string is asserted by
   [`tests/bats/test_manifest_drift_localization.bats`](../tests/bats/test_manifest_drift_localization.bats);
   keep it stable.
4. **Atomic writes.** Write every target through `generator_io.atomic_write`
   from [`scripts/generator_io.py`](../scripts/generator_io.py), which
   preserves target permissions and replaces complete content;
   `generator_io.sync` already does. Cleanup is best effort; the
   original write error propagates if cleanup also fails.
5. **Canary test.** Add a bats test that pins the *presence* of the marker
   or region. Without this, a future refactor that strips the cog markers
   would make `--check` silently pass with nothing to check. See
   [`tests/bats/test_persona_surfaces_generator_check.bats`](../tests/bats/test_persona_surfaces_generator_check.bats)
   for the existing example.
   [`tests/bats/test_regen_wiring.bats`](../tests/bats/test_regen_wiring.bats)
   already fails when a `scripts/regen_*.py` generator is missing from
   `scripts/regen.sh`.

## How to add a new surface with cog

For Markdown, YAML, shell, Python, or any other format that supports
HTML-style comments:

1. Add a markered region in the target file:

   ```text
   <!--[[[cog
   import _personas_for_cog as P  # or your own helper
   for item in P.something():
       cog.outl(f"- {item}")
   ]]]-->
   ...generated content (cog overwrites this)...
   <!--[[[end]]]-->
   ```

   Keep the inline Python tiny, one or two lines that delegate to a helper
   in `scripts/`. See [`scripts/_personas_for_cog.py`](../scripts/_personas_for_cog.py).
2. Append the file path to [`scripts/cogfiles.txt`](../scripts/cogfiles.txt).
3. Run `scripts/regen.sh` to populate the region.
4. Add a canary bats test that greps for the open and close marker strings
   in the target file (model on
   [`test_persona_surfaces_generator_check.bats`](../tests/bats/test_persona_surfaces_generator_check.bats)).

`scripts/regen.sh` already runs cog over every file in `cogfiles.txt`; nothing
else needs wiring.

## How to add a new surface with a standalone script

For JSON, TOML, or other comment-less formats:

1. Name it `scripts/regen_<surface>.py`; the wiring test finds generators by
   that pattern. Copy the shape of
   [`scripts/regen_adversary_caps.py`](../scripts/regen_adversary_caps.py):
   - `--check` / `--write` modes (mutually exclusive argparse group, default
     to `--check`).
   - Manifest loader: `from personas_manifest import load_manifest` for
     `reviewers/personas.yaml`.
   - Surgical rewrite: parse with `json.loads` (or equivalent) to **validate
     that the target path exists** before touching anything, then splice the
     new content into the existing file text. **Do not** round-trip the
     whole file through `json.dumps`; that destroys intentional inline
     formatting elsewhere in the file.
   - Render replacement content via the format's parser (`json.dumps`, etc.)
     not by hand-building strings, so escaping is always correct.
   - Run the read, diff-or-write loop through `generator_io.sync`, splice
     marker regions with `generator_io.sub_region`, and end on a target you
     cannot rewrite with `generator_io.fail`;
     [`scripts/regen_adversary_caps.py`](../scripts/regen_adversary_caps.py)
     uses all three.
   - Exit codes per rule 2; fix hint string per rule 3.
2. Add the script name to the `GENERATORS` array in
   [`scripts/regen.sh`](../scripts/regen.sh), which runs it in both modes.
3. Add a canary bats test (same as the cog path).

## Pointers

- [`scripts/regen.sh`](../scripts/regen.sh), user-facing regen entrypoint
- [`scripts/regen-check.sh`](../scripts/regen-check.sh), CI check entrypoint (`regen.sh --check`)
- [`scripts/regen_adversary_caps.py`](../scripts/regen_adversary_caps.py), reference standalone-script implementation
- [`scripts/generator_io.py`](../scripts/generator_io.py), shared exit codes, region splice, check-or-write loop and atomic replacement
- [`scripts/_personas_for_cog.py`](../scripts/_personas_for_cog.py), helper imported by inline cog snippets
- [`docs/editing-personas.md`](editing-personas.md), workflow for the specific personas-manifest case

Use `regen.sh` and `regen-check.sh` for new callers. The `personas-*` scripts remain compatibility entrypoints.
