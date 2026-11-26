#!/usr/bin/env python3
"""Decide whether two reviewer findings match for dedupe/promotion.

A match is: same file AND |line_a - line_b| <= 5 AND token_overlap(summary_a,
summary_b) >= 0.6.

token_overlap is Jaccard similarity over lowercased word-sets with English
stop-word filtering applied to both summaries.

Used by SKILL.md §4c synthesize (dedupe and multi-persona promotion) and §4d.0.5
post-adversary re-synthesize (adversary endorsement). Synthesizer prompts invoke
this script per candidate pair.

Inputs: two JSON objects, each with at least `file: string`, `line: integer`,
`summary: string`. Either both as file args, or one as `-` for stdin (only one
`-` allowed per invocation).

Exit codes:
  0 - match
  1 - no match
  2 - usage/parse error (missing field, invalid JSON, bad CLI form)

Errors go to stderr; stdout stays clean so callers can pipe.
"""

import json
import sys
from pathlib import Path

from finding_matcher import is_match


def _load(arg: str) -> dict:
    if arg == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(arg).read_text(encoding="utf-8")
    return json.loads(raw)


def _require(obj: dict, key: str, label: str) -> None:
    if key not in obj:
        print(f"ERROR: {label}: missing required field '{key}'", file=sys.stderr)
        raise SystemExit(2)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: match_findings.py <a.json|-> <b.json|->", file=sys.stderr)
        return 2

    if sys.argv[1] == "-" and sys.argv[2] == "-":
        print("ERROR: at most one of the two args may be '-'", file=sys.stderr)
        return 2

    try:
        a = _load(sys.argv[1])
        b = _load(sys.argv[2])
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read input: {e}", file=sys.stderr)
        return 2

    for label, obj in (("a", a), ("b", b)):
        if not isinstance(obj, dict):
            print(f"ERROR: {label}: expected JSON object", file=sys.stderr)
            return 2
        _require(obj, "file", label)
        _require(obj, "line", label)
        _require(obj, "summary", label)
        if not isinstance(obj["file"], str):
            print(f"ERROR: {label}: 'file' must be string", file=sys.stderr)
            return 2
        if not isinstance(obj["line"], int) or isinstance(obj["line"], bool):
            print(f"ERROR: {label}: 'line' must be integer", file=sys.stderr)
            return 2
        if not isinstance(obj["summary"], str):
            print(f"ERROR: {label}: 'summary' must be string", file=sys.stderr)
            return 2

    if not is_match(a, b):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
