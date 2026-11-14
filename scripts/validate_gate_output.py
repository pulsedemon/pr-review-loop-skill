#!/usr/bin/env python3
# validate_gate_output.py — validate one delta-gate subagent's JSON output
# against reviewers/gate.schema.json. Used by §4a.1 before panel selection.
#
# A failed/malformed gate output is fail-open at the orchestrator level: the
# persona is treated as relevant and runs. This script's only job is to tell
# the orchestrator whether a given gate output can be trusted.
#
# stdin:  one gate output object.
# stdout: nothing (errors go to stderr).
#
# exit codes:
#   0 — output is valid against the schema
#   2 — output is missing, malformed, or schema-invalid
#   exit 1 is intentionally unused; callers need only test for a non-zero exit.

import argparse
import json
import sys
from pathlib import Path

import jsonschema
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "reviewers" / "gate.schema.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a delta gate response.")
    parser.add_argument("--reviewer")
    args = parser.parse_args()
    try:
        schema = json.loads(SCHEMA_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"validate_gate_output: cannot load schema ({exc})", file=sys.stderr)
        return 2
    try:
        Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as exc:
        print(f"validate_gate_output: schema is malformed ({exc})", file=sys.stderr)
        return 2

    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"validate_gate_output: stdin is not valid JSON ({exc})", file=sys.stderr)
        return 2

    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        print(f"validate_gate_output: schema validation failed ({exc.message})", file=sys.stderr)
        return 2

    if args.reviewer is not None and data["reviewer"] != args.reviewer:
        print(
            f"validate_gate_output: expected reviewer {args.reviewer!r}, got {data['reviewer']!r}",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
