import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


def reject_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def main():
    try:
        schema = json.loads((Path(__file__).parent / "templates/state.schema.json").read_text())
        raw = sys.stdin.read()
        record = json.loads(raw, parse_constant=reject_constant)
        Draft202012Validator(schema).validate(record)
    except (OSError, ValueError, ValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.write(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
