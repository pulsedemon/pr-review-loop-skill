"""Regenerate the §4d.0 adversary cap mirrors from manifests/adversary-caps.yaml.

Surfaces (all three written from one manifest value):
  - templates/state.schema.json: both .properties.shallow_adversary_runs.maximum
    and .properties.shallow_approval_adversary_runs.maximum are set to `cap`.
  - scripts/_adversary_caps.sh: the cog region body (preset-value guard plus
    the `readonly ADVERSARY_CAP=N` line) is rewritten as a unit; any other
    content placed between the cog markers is replaced.
  - docs/adversary.md: the literal cap inside the regen-block region is
    rewritten.

Modes mirror cog: --check exits 0/5, --write rewrites in place atomically.
Manifest errors exit 3.

Spec: docs/generators.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import generator_io
import yaml

_DRIFT_EXIT = 5
_MANIFEST_ERROR_EXIT = 3

_HELPER_REGION = re.compile(
    r"(# \[\[\[cog: adversary_caps_sh \]\]\]\n)(.*?)(# \[\[\[end\]\]\])",
    re.DOTALL,
)
_DOC_REGION = re.compile(
    r"(<!-- regen:adversary-caps:start -->\n)(.*?)(<!-- regen:adversary-caps:end -->)",
    re.DOTALL,
)
_SCHEMA_FIELDS = ("shallow_adversary_runs", "shallow_approval_adversary_runs")


def _regen_schema(text: str, cap: int) -> str:
    # Pre-flight: confirm the schema parses and the target paths exist. Catches
    # structural changes (renamed property, moved path) with a specific message
    # instead of letting the surgical regex silently miss.
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"regen_adversary_caps: templates/state.schema.json is not valid JSON: {e}"
        ) from e
    for field in _SCHEMA_FIELDS:
        try:
            data["properties"][field]["maximum"]
        except (KeyError, TypeError) as e:
            raise SystemExit(
                f"regen_adversary_caps: could not find properties.{field}.maximum in "
                "templates/state.schema.json. Has the schema structure changed?"
            ) from e

    new = text
    for field in _SCHEMA_FIELDS:
        pattern = re.compile(
            r'("' + re.escape(field) + r'"\s*:\s*\{[^}]*?"maximum"\s*:\s*)(\d+)',
            re.DOTALL,
        )
        new, n = pattern.subn(lambda m: m.group(1) + str(cap), new, count=1)
        if n != 1:
            raise SystemExit(
                f"regen_adversary_caps: properties.{field}.maximum exists in the "
                "parsed schema but the slice locator regex did not match. The "
                "schema's formatting around that field may have changed."
            )
    return new


def _regen_helper(text: str, cap: int) -> str:
    body = (
        f'if [[ -n "${{ADVERSARY_CAP:-}}" && "${{ADVERSARY_CAP}}" != "{cap}" ]]; then\n'
        f"  echo \"ERROR: ADVERSARY_CAP is preset to '${{ADVERSARY_CAP}}', "
        f"expected '{cap}'.\" >&2\n"
        f'  echo "       Unset it before sourcing scripts/_adversary_caps.sh." >&2\n'
        f"  return 1 2>/dev/null || exit 1\n"
        f"fi\n"
        f"readonly ADVERSARY_CAP={cap}\n"
    )
    new, n = _HELPER_REGION.subn(lambda m: m.group(1) + body + m.group(3), text, count=1)
    if n != 1:
        raise SystemExit(
            "regen_adversary_caps: could not find adversary_caps_sh cog region in "
            "scripts/_adversary_caps.sh. Has the file's cog markers been edited?"
        )
    return new


def _regen_doc(text: str, cap: int) -> str:
    body = f"The cap is {cap} (see ADVERSARY_CAP in templates/state.schema.json).\n"
    new, n = _DOC_REGION.subn(lambda m: m.group(1) + body + m.group(3), text, count=1)
    if n != 1:
        raise SystemExit(
            "regen_adversary_caps: could not find regen:adversary-caps region in "
            "docs/adversary.md. Has the doc's region markers been edited?"
        )
    return new


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    repo = Path(__file__).resolve().parent.parent
    parser.add_argument("--manifest", type=Path, default=repo / "manifests" / "adversary-caps.yaml")
    parser.add_argument("--schema", type=Path, default=repo / "templates" / "state.schema.json")
    parser.add_argument("--helper", type=Path, default=repo / "scripts" / "_adversary_caps.sh")
    parser.add_argument("--doc", type=Path, default=repo / "docs" / "adversary.md")
    args = parser.parse_args(argv)
    if not args.write:
        args.check = True

    try:
        manifest = yaml.safe_load(args.manifest.read_text())
        cap = int(manifest["cap"])
    except (FileNotFoundError, KeyError, TypeError, ValueError, yaml.YAMLError) as e:
        print(f"regen_adversary_caps: manifest error: {e}", file=sys.stderr)
        return _MANIFEST_ERROR_EXIT

    targets = [
        ("schema", args.schema, _regen_schema),
        ("helper", args.helper, _regen_helper),
        ("doc", args.doc, _regen_doc),
    ]
    drifted = False
    for _label, path, regen in targets:
        before = path.read_text()
        after = regen(before, cap)
        if before == after:
            continue
        if args.check:
            generator_io.emit_drift_diff(path, before, after)
            drifted = True
        else:
            generator_io.atomic_write(path, after)

    if args.check and drifted:
        print(
            "\nregen_adversary_caps: cap mirrors are out of date. "
            "Run scripts/regen.sh to regenerate.",
            file=sys.stderr,
        )
        return _DRIFT_EXIT
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
