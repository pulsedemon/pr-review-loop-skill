# Manifest-driven generators

This doc captures the **generator convention** used to keep manifest-derived
surfaces in sync. The first instance is `reviewers/personas.yaml` driving the
SKILL.md "Reviewer personas" bullet list and the `reviewer.enum` in
`reviewers/output.schema.json` (see [`editing-personas.md`](editing-personas.md)
for that specific workflow). This doc is for **adding new generated surfaces**
later, so they all behave the same way.

## Why this exists

The repo's editing rule is "manifest is source of truth; everything else syncs
to it." Sync was originally enforced by bats tests that compared the manifest
to each dependent surface. That works, but every new surface adds another
hand-written sync test and another way for an editor to "fix" the wrong end of
the comparison. Generators flip the polarity: edit the manifest, run one
command, and every dependent surface is regenerated. Drift becomes impossible
to commit (CI runs `--check`) rather than something the developer is trusted
to notice.

## Format → tool

| Comment syntax in target file | Generator tool | Why |
| --- | --- | --- |
| HTML comments (`<!-- -->`): Markdown, HTML, XML | [cog](https://nedbatchelder.com/code/cog/) with `<!--[[[cog ... ]]]-->` markers | cog ships HTML-comment-style markers as the default; edits in place with `-r`. |
| Hash comments (`#`): YAML, shell, Python, TOML | cog with `# [[[cog ... ]]]` markers | Same `-r` flow; just swap the marker style. |
| No comments: JSON, most lockfiles | Standalone Python script following [`scripts/regen_schema_enum.py`](../scripts/regen_schema_enum.py)'s shape | No marker possible. Splice via parser-validated regex. |

Cog is the default; reach for a standalone script only when the target format
has no comment syntax at all.

## Contract every generator must honor

These rules apply equally to cog-managed regions and standalone scripts.

1. **Two modes.** `--check` (validates, exits non-zero on drift) and `--write`
   (rewrites in place). The orchestrator scripts
   [`scripts/regen.sh`](../scripts/regen.sh) and
   [`scripts/regen-check.sh`](../scripts/regen-check.sh) run every
   generator in the appropriate mode.
2. **Exit codes.** `0` ok, `3` manifest error, `5` drift detected. Matches
   cog's semantics so the orchestrator can chain generators without
   translating exit codes.
3. **Drift output.** On drift, emit a unified diff to stderr and a literal
   fix hint: `Run scripts/regen.sh to regenerate ...`. The literal
   string is asserted by
   [`tests/bats/test_manifest_drift_localization.bats`](../tests/bats/test_manifest_drift_localization.bats);
   keep it stable.
4. **Atomic writes.** Call `generator_io.atomic_write` from
   [`scripts/generator_io.py`](../scripts/generator_io.py) to preserve target
   permissions and replace complete content. Cleanup is best effort; the
   original write error propagates if cleanup also fails.
5. **Canary test.** Add a bats test that pins the *presence* of the marker
   or region. Without this, a future refactor that strips the cog markers
   (or removes the standalone script's invocation from the orchestrator)
   would make `--check` silently pass with nothing to check. See
   [`tests/bats/test_persona_surfaces_generator_check.bats`](../tests/bats/test_persona_surfaces_generator_check.bats)
   for the existing example.

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

The orchestrator scripts already handle cog-managed files via `cogfiles.txt`;
nothing else needs wiring.

## How to add a new surface with a standalone script

For JSON, TOML, or other comment-less formats:

1. Copy the shape of [`scripts/regen_schema_enum.py`](../scripts/regen_schema_enum.py):
   - `--check` / `--write` modes (mutually exclusive argparse group, default
     to `--check`).
   - Manifest loader: `from personas_manifest import load_manifest`.
   - Surgical rewrite: parse with `json.loads` (or equivalent) to **validate
     that the target path exists** before touching anything, then splice the
     new content into the existing file text. **Do not** round-trip the
     whole file through `json.dumps`; that destroys intentional inline
     formatting elsewhere in the file.
   - Render replacement content via the format's parser (`json.dumps`, etc.)
     not by hand-building strings, so escaping is always correct.
   - Shared output via `generator_io.atomic_write` and `generator_io.emit_drift_diff`.
   - Exit codes 0 / 3 / 5; drift diff to stderr; fix hint string.
2. Wire into both orchestrator scripts:
   - [`scripts/regen.sh`](../scripts/regen.sh): append
     `python3 "$ROOT/scripts/your_script.py" --write`.
   - [`scripts/regen-check.sh`](../scripts/regen-check.sh): append
     `python3 "$ROOT/scripts/your_script.py" --check`.
   Use the existing entrypoints for regen and check; CI runs `regen-check.sh`.
3. Add a canary bats test (same as the cog path).

## Pointers

- [`scripts/regen.sh`](../scripts/regen.sh), user-facing regen entrypoint
- [`scripts/regen-check.sh`](../scripts/regen-check.sh), CI / pre-commit check entrypoint
- [`scripts/regen_schema_enum.py`](../scripts/regen_schema_enum.py), reference standalone-script implementation
- [`scripts/generator_io.py`](../scripts/generator_io.py), shared atomic replacement and diff output
- [`scripts/_personas_for_cog.py`](../scripts/_personas_for_cog.py), helper imported by inline cog snippets
- [`docs/editing-personas.md`](editing-personas.md), workflow for the specific personas-manifest case

Use `regen.sh` and `regen-check.sh` for new callers. The `personas-*` scripts remain compatibility entrypoints.
