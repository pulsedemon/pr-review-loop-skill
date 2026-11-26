#!/usr/bin/env python3
"""compare the committed manifest with the weekly workflow's merged PR set.

exit 0 when the manifest covers every merged PR, 1 when it does not, 2 on a
usage or fetch error. manifest rows outside the query window are allowed.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from collect_pr_corpus import FetchResponseError, list_merged_prs, read_manifest


def missing_from_manifest(
    manifest: Path, owner: str, repo: str, merged_prs: list[int]
) -> list[int]:
    manifested = {
        pr for m_owner, m_repo, pr in read_manifest(manifest) if (m_owner, m_repo) == (owner, repo)
    }
    return sorted(set(merged_prs) - manifested)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail when the manifest is missing merged PRs")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--merged-since", required=True, help="ISO date (YYYY-MM-DD)")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    if not args.manifest.is_file():
        print(f"check_manifest_drift: no manifest at {args.manifest}", file=sys.stderr)
        return 2

    # A gh that is absent (FileNotFoundError) or returns something other than
    # the requested JSON (JSONDecodeError) means the merged set is unknown, not
    # empty. Letting either escape would exit non-zero on a stack trace, which
    # reads in the workflow log like drift the operator has to go chase.
    try:
        merged = list_merged_prs(args.owner, args.repo, args.merged_since)
    except subprocess.CalledProcessError as e:
        print(
            f"check_manifest_drift: cannot list merged PRs for {args.owner}/{args.repo}\n"
            f"stderr: {e.stderr}",
            file=sys.stderr,
        )
        return 2
    except (FileNotFoundError, json.JSONDecodeError, FetchResponseError) as e:
        print(
            f"check_manifest_drift: cannot list merged PRs for {args.owner}/{args.repo}\n"
            f"{type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return 2

    # Same reasoning as the fetch handlers above: a manifest that will not parse
    # leaves coverage unknown, and a traceback here exits non-zero looking like
    # drift. ValueError covers a non-numeric pr, KeyError a missing column.
    try:
        missing = missing_from_manifest(args.manifest, args.owner, args.repo, merged)
    except (ValueError, KeyError, OSError) as e:
        print(
            f"check_manifest_drift: cannot read {args.manifest}\n{type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return 2
    if missing:
        listed = ",".join(str(pr) for pr in missing)
        print(
            f"check_manifest_drift: {args.manifest} is missing "
            f"{len(missing)} merged PR(s): {listed}\n"
            "the weekly run collects these; manifest-based collection does not. "
            "append the missing entries when refreshing the manifest.",
            file=sys.stderr,
        )
        return 1

    print(f"check_manifest_drift: manifest covers all {len(merged)} merged PR(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
