#!/usr/bin/env python3
"""Validate one reviewer subagent's JSON output against reviewers/output.schema.json.

Reads JSON from stdin (or the path passed as $1). Exits 0 on a valid object,
1 on any failure (parse error, schema violation, wrong shape). Errors go to
stderr; stdout stays clean so the caller can pipe through.

invalid output is a failed review; callers record the error and do not
synthesize a replacement response.
"""

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

REPO = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO / "reviewers" / "output.schema.json"
EXPECTED_SCHEMA_ID_PREFIX = (
    "https://github.com/pulsedemon/pr-review-loop-skill/schemas/reviewer-output/"
)
EXPECTED_SCHEMA_VERSION = "0.1.0"
EXPECTED_SCHEMA_ID = f"{EXPECTED_SCHEMA_ID_PREFIX}{EXPECTED_SCHEMA_VERSION}.json"


def load_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    schema_id = schema.get("$id")
    if schema_id != EXPECTED_SCHEMA_ID:
        raise ValueError(
            f"schema $id {schema_id!r} does not match expected "
            f"{EXPECTED_SCHEMA_ID!r}; bumping schema version requires "
            f"updating EXPECTED_SCHEMA_VERSION in {Path(__file__).name}"
        )
    return Draft202012Validator(schema)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--reviewer")
    args = parser.parse_args()

    try:
        validator = load_validator()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SchemaError, ValueError) as e:
        print(f"ERROR: invalid or unreadable reviewer schema: {e}", file=sys.stderr)
        return 1

    try:
        if args.path is not None:
            raw = args.path.read_text()
        else:
            raw = sys.stdin.read()
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"ERROR: invalid JSON or unreadable input: {e}", file=sys.stderr)
        return 1

    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        for err in errors:
            loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
            print(f"ERROR: {loc}: {err.message}", file=sys.stderr)
        return 1

    if args.reviewer is not None and data["reviewer"] != args.reviewer:
        print(
            f"ERROR: expected reviewer {args.reviewer!r}, got {data['reviewer']!r}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
