#!/usr/bin/env python3
"""Print the response object from a Witch familiar report as JSON.

The response is the last JSON object that starts a line outside a code fence and
is followed only by blank lines, Witch's `Permission denied:` lines or its
`This run was suspended for ` note. Exits 1 when no object qualifies. The object
is printed as decoded, never repaired. Contract: docs/model-overrides.md#witch.
"""

import argparse
import json
import sys
from pathlib import Path

FENCE = "```"
WITCH_TRAILERS = ("Permission denied:", "This run was suspended for ")


def _trailer_only(text: str) -> bool:
    return all(not line.strip() or line.startswith(WITCH_TRAILERS) for line in text.splitlines())


def last_object(text: str) -> dict | None:
    decoder = json.JSONDecoder()
    found = None
    offset = 0
    fences = 0
    for line in text.splitlines(keepends=True):
        if line.startswith(FENCE):
            fences += 1
        elif line.startswith("{") and fences % 2 == 0:
            try:
                value, end = decoder.raw_decode(text, offset)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(value, dict) and _trailer_only(text[end:]):
                    found = value
        offset += len(line)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="print a familiar report's response object")
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    value = last_object(args.report.read_text())
    if value is None:
        print(f"familiar_response: no response object in {args.report}", file=sys.stderr)
        return 1
    print(json.dumps(value))
    return 0


if __name__ == "__main__":
    sys.exit(main())
