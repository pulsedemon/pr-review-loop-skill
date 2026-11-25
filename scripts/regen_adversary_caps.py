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
Manifest and target errors exit 3.

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
        generator_io.fail(
            f"regen_adversary_caps: templates/state.schema.json is not valid JSON: {e}"
        )
    for field in _SCHEMA_FIELDS:
        try:
            data["properties"][field]["maximum"]
        except (KeyError, TypeError):
            generator_io.fail(
                f"regen_adversary_caps: could not find properties.{field}.maximum in "
                "templates/state.schema.json. Has the schema structure changed?"
            )

    new = text
    for field in _SCHEMA_FIELDS:
        pattern = re.compile(
            r'("' + re.escape(field) + r'"\s*:\s*\{[^}]*?"maximum"\s*:\s*)(\d+)',
            re.DOTALL,
        )
        new, n = pattern.subn(lambda m: m.group(1) + str(cap), new, count=1)
        if n != 1:
            generator_io.fail(
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
    return generator_io.sub_region(
        _HELPER_REGION,
        text,
        body,
        "regen_adversary_caps: could not find adversary_caps_sh cog region in "
        "scripts/_adversary_caps.sh. Have the file's cog markers been edited?",
    )


def _regen_doc(text: str, cap: int) -> str:
    body = f"The cap is {cap} (see ADVERSARY_CAP in templates/state.schema.json).\n"
    return generator_io.sub_region(
        _DOC_REGION,
        text,
        body,
        "regen_adversary_caps: could not find regen:adversary-caps region in "
        "docs/adversary.md. Have the doc's region markers been edited?",
    )


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
        return generator_io.MANIFEST_ERROR_EXIT

    drifted = generator_io.sync(
        [
            (args.schema, lambda text: _regen_schema(text, cap)),
            (args.helper, lambda text: _regen_helper(text, cap)),
            (args.doc, lambda text: _regen_doc(text, cap)),
        ],
        check=args.check,
    )

    if args.check and drifted:
        print(
            "\nregen_adversary_caps: cap mirrors are out of date. "
            "Run scripts/regen.sh to regenerate.",
            file=sys.stderr,
        )
        return generator_io.DRIFT_EXIT
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
