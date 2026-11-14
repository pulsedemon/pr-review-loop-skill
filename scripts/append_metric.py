#!/usr/bin/env python3
# append a single JSON object (read from stdin) as one line to
# <git-dir>/pr-loop/metrics.jsonl. owns no business logic; callers in
# SKILL §4i and Step 5 construct the record.
#
# exit codes:
#   0 - line appended
#   1 - usage / harness error (no git dir, etc.)
#   2 - stdin payload is not a single valid JSON object (rejects NaN/Infinity)
#   3 - flock or write failure (OSError)

import fcntl
import json
import subprocess
import sys
from pathlib import Path


def _git_dir() -> Path:
    try:
        out = subprocess.check_output(["git", "rev-parse", "--git-dir"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"append_metric: not in a git repo ({exc})", file=sys.stderr)
        sys.exit(1)
    return Path(out)


def _reject_nonfinite(token: str):
    # json.loads accepts NaN/Infinity by default; downstream jq consumers
    # cannot parse them, so any non-finite constant must fail loudly.
    raise ValueError(f"non-finite JSON constant: {token}")


def main() -> int:
    raw = sys.stdin.read()
    try:
        record = json.loads(raw, parse_constant=_reject_nonfinite)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"append_metric: stdin is not valid JSON ({exc})", file=sys.stderr)
        return 2
    if not isinstance(record, dict):
        print("append_metric: stdin must be a JSON object", file=sys.stderr)
        return 2

    target = _git_dir() / "pr-loop" / "metrics.jsonl"
    line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            # exclusive lock so concurrent §4i + Step 5 writers cannot interleave.
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.write(line)
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        print(
            f"append_metric: write failed ({exc.errno}: {exc.strerror or exc})",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
