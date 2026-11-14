import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


def main():
    try:
        schema = json.loads((Path(__file__).parent / "templates/state.schema.json").read_text())
        record = json.load(sys.stdin)
        Draft202012Validator(schema).validate(record)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
