"""Regenerate the `reviewer` enum in reviewers/output.schema.json from
reviewers/personas.yaml.

JSON has no comment syntax, so cog markers can't live inside the schema
itself. This script does the equivalent: a json-validated, regex-anchored
slice rewrite of the `enum` array directly under `properties.reviewer`.
The schema's hand-formatting (inline arrays/objects elsewhere) is
preserved outside the reviewer.enum body.

Modes:
  --check   (default) exit 0 if file matches generated content; exit 5
            with a unified diff to stderr otherwise.
  --write   rewrite the file in place (atomic via .tmp + os.replace).

Exit codes: 0 ok, 3 manifest or target error, 5 drift detected.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import generator_io
from personas_manifest import ManifestError, load_manifest

# Locates the `reviewer.enum` slice for in-place replacement. Anchored on
# the property key + type so we never grab a sibling property's enum by
# accident. Content production is handled by json.dumps below; this regex
# only finds where to splice.
_ENUM_SLICE = re.compile(
    r'("reviewer"\s*:\s*\{\s*"type"\s*:\s*"string"\s*,\s*"enum"\s*:\s*\[)'
    r"([^\]]*)"
    r"(\])",
    re.DOTALL,
)


def _render_enum_body(names: list[str]) -> str:
    # Render via json.dumps so any future name that needs escaping stays
    # valid JSON. The schema indents enum items at 8 spaces; json.dumps
    # gives us 2-space indent which we shift by re-indenting the inner
    # lines. The closing bracket sits at 6-space indent in the schema, so
    # we strip the trailing "]" and let the surrounding splice supply it.
    body = json.dumps(names, indent=2)
    inner_lines = body.splitlines()[1:-1]  # drop "[" and "]"
    shifted = ["        " + line.lstrip() for line in inner_lines]
    return "\n" + "\n".join(shifted) + "\n      "


def _regenerated(text: str, names: list[str]) -> str:
    # Pre-flight: confirm the schema parses and the target path exists.
    # This catches structural changes (renamed property, moved path) with
    # a specific message instead of letting the regex silently miss.
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        generator_io.fail(f"regen_schema_enum: reviewers/output.schema.json is not valid JSON: {e}")
    try:
        data["properties"]["reviewer"]["enum"]
    except (KeyError, TypeError):
        generator_io.fail(
            "regen_schema_enum: could not find properties.reviewer.enum in "
            "reviewers/output.schema.json. Has the schema structure changed?"
        )

    body = _render_enum_body(names)
    match = _ENUM_SLICE.search(text)
    if match is None:
        generator_io.fail(
            "regen_schema_enum: properties.reviewer.enum exists in the parsed "
            "schema but the slice locator regex did not match. The schema's "
            "formatting around the reviewer.enum block may have changed."
        )
    return text[: match.start(2)] + body + text[match.end(2) :]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="diff vs disk (default)")
    mode.add_argument("--write", action="store_true", help="rewrite file in place")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "reviewers" / "personas.yaml",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "reviewers" / "output.schema.json",
    )
    args = parser.parse_args(argv)
    if not args.write:
        args.check = True

    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as e:
        print(f"regen_schema_enum: manifest error: {e}", file=sys.stderr)
        return generator_io.MANIFEST_ERROR_EXIT

    names = [p.name for p in manifest.panel] + [manifest.adversary.name]
    try:
        current = args.schema.read_text()
    except (OSError, UnicodeDecodeError) as e:
        print(f"regen_schema_enum: failed to read {args.schema}: {e}", file=sys.stderr)
        return generator_io.MANIFEST_ERROR_EXIT
    regenerated = _regenerated(current, names)

    if args.check:
        if current == regenerated:
            return 0
        generator_io.emit_drift_diff(args.schema, current, regenerated)
        print(
            "\nregen_schema_enum: reviewer.enum is out of date. "
            "Run scripts/regen.sh to regenerate.",
            file=sys.stderr,
        )
        return generator_io.DRIFT_EXIT

    if current != regenerated:
        generator_io.atomic_write(args.schema, regenerated)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
