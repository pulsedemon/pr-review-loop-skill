#!/usr/bin/env python3
"""Helpers for validating scenario markdown status blocks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


class ValidationError(ValueError):
    """Raised when a scenario markdown file is malformed."""


def extract_validation_status(path: Path) -> str:
    """Return the `## Validation status` section from one scenario file."""
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ValidationError(f"failed to read {path}: {exc}") from exc

    start = None
    for index, line in enumerate(lines):
        if line == "## Validation status":
            start = index
            break
    if start is None:
        raise ValidationError(f"{path} is missing '## Validation status' section")

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break

    return "\n".join(lines[start:end]).rstrip()


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Scenario validation helpers.")
    parser.add_argument(
        "--section",
        type=Path,
        metavar="SCENARIO_FILE",
        required=True,
        help="print the exact ## Validation status section for one scenario markdown file",
    )
    args = parser.parse_args(argv)

    try:
        print(extract_validation_status(args.section))
    except ValidationError as exc:
        print(f"validation error: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
