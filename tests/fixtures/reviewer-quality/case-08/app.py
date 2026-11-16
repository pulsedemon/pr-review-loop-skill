import json
import sys


def reject_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def fail(message):
    print(message, file=sys.stderr)
    return 2


def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        record = json.loads(raw, parse_constant=reject_constant)
    except (ValueError, RecursionError) as exc:
        return fail(f"invalid JSON: {exc}")
    if not isinstance(record, dict):
        return fail("record must be an object")
    for field in ("addressed", "deferred"):
        entries = record[field]
        if not isinstance(entries, list):
            return fail(f"{field} must be an array")
        for entry in entries:
            if not isinstance(entry, dict):
                return fail(f"{field} entries must be objects")
            pr, cause = entry.get("pr"), entry.get("cause")
            if not isinstance(pr, str) or not isinstance(cause, str):
                return fail(f"{field} entries require string pr and cause")
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
