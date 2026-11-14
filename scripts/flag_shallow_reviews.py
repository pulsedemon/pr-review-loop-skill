#!/usr/bin/env python3
# flag_shallow_reviews.py — identify panel reviewers that returned an
# approve verdict without recording what they read. The rule lives in
# SKILL.md §4b/§4c: a reviewer with `verdict: "approve"` and missing or
# empty `evidence.files_read` is flagged shallow for the iteration.
#
# Only `verdict: "approve"` is ever flag-eligible. Any other verdict
# (request_changes, comment) is never flagged, regardless of evidence shape.
#
# stdin:  JSON array of reviewer outputs (one per panelist).
# stdout: {"shallow_review": ["<name>", ...]}  (alphabetical for stable diffs)
#
# exit codes:
#   0 — emitted shallow_review list (may be empty)
#   2 — usage / schema error (stdin is not a JSON array of objects)

import json
import sys


def is_shallow(reviewer: dict) -> bool:
    if reviewer.get("verdict") != "approve":
        return False
    evidence = reviewer.get("evidence")
    if not isinstance(evidence, dict):
        return True
    files_read = evidence.get("files_read")
    if not isinstance(files_read, list) or len(files_read) == 0:
        return True
    return False


def main() -> int:
    raw = sys.stdin.read()
    try:
        reviewers = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"flag_shallow_reviews: stdin is not valid JSON ({exc})", file=sys.stderr)
        return 2
    if not isinstance(reviewers, list):
        print("flag_shallow_reviews: stdin must be a JSON array", file=sys.stderr)
        return 2

    flagged = []
    for r in reviewers:
        if not isinstance(r, dict):
            print("flag_shallow_reviews: array entries must be objects", file=sys.stderr)
            return 2
        name = r.get("reviewer")
        if not isinstance(name, str):
            print(
                "flag_shallow_reviews: each reviewer object needs a string `reviewer` field",
                file=sys.stderr,
            )
            return 2
        if is_shallow(r):
            flagged.append(name)

    json.dump({"shallow_review": sorted(flagged)}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
