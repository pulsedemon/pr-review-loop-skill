#!/usr/bin/env python3
"""emit corpus-manifest rows for merged PRs the loop has run on.

a PR counts when one of its top-level issue comments carries SUMMARY_MARKER,
which is the same signal `collect_pr_corpus.py` reads. rows go to stdout in
manifest order (`owner,repo,pr`) so the output appends straight onto
corpus-manifest.csv; progress and warnings go to stderr.

read comments through paginated GraphQL queries; GitHub search can omit
comments containing the summary marker.

exit 0 on success, 2 on a usage or fetch error, 3 when a PR's comments
overflowed the page so the row set may be short.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_pr_corpus import SUMMARY_MARKER  # type: ignore[import-not-found]  # noqa: E402

# PRs per request, and comments per PR within it. GraphQL caps either connection
# at 100; the outer page sits at 50 because 50x100 nodes is a large enough
# response to slow the API down without buying fewer round trips worth having.
_PR_PAGE = 50
_COMMENT_PAGE = 100

_QUERY = """
query($owner:String!, $name:String!, $prPage:Int!, $commentPage:Int!, $cursor:String) {
  repository(owner:$owner, name:$name) {
    pullRequests(states:MERGED, first:$prPage, after:$cursor,
                 orderBy:{field:CREATED_AT, direction:ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        comments(first:$commentPage) {
          totalCount
          nodes { body }
        }
      }
    }
  }
}
"""


def scan_repo(owner: str, repo: str) -> tuple[list[int], list[int], list[int]]:
    """Return (PRs carrying the marker, every merged PR seen, PRs only partly readable)."""
    cursor: str | None = None
    hits: list[int] = []
    seen: list[int] = []
    partial: list[int] = []
    while True:
        cmd = [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={_QUERY}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={repo}",
            "-F",
            f"prPage={_PR_PAGE}",
            "-F",
            f"commentPage={_COMMENT_PAGE}",
        ]
        if cursor:
            cmd += ["-F", f"cursor={cursor}"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        page = json.loads(proc.stdout)["data"]["repository"]["pullRequests"]
        for node in page["nodes"]:
            seen.append(node["number"])
            comments = node["comments"]
            visible = [c for c in comments["nodes"] if c]
            if any(SUMMARY_MARKER in (c["body"] or "") for c in visible):
                hits.append(node["number"])
                continue
            # No marker among what was readable, and part of the PR was not:
            # either the page cut the comments off, or GraphQL nulled a node the
            # token cannot resolve. The missing one may be the summary.
            if comments["totalCount"] > _COMMENT_PAGE or len(visible) != len(comments["nodes"]):
                partial.append(node["number"])
        if not page["pageInfo"]["hasNextPage"]:
            return sorted(hits), seen, partial
        cursor = page["pageInfo"]["endCursor"]


# Terminal statuses that complete the loop without posting a summary comment,
# by design rather than by failure (docs/step5-summary.md). An archive carrying
# one is not evidence the run stopped early.
_NO_COMMENT_STATUSES = frozenset({"dry_run_complete", "setup_error", "review_incomplete"})


def _git_dir(checkout: Path) -> Path:
    """Resolve a checkout's git dir, the way the loop itself does.

    In a worktree `.git` is a file pointing elsewhere and `state_init.sh` writes
    under `git rev-parse --git-dir`, so assuming a directory silently skipped the
    archive check there. Falls back to the plain layout when git cannot answer,
    which keeps a bare directory of archives readable.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return checkout / ".git"
    git_dir = Path(proc.stdout.strip())
    return git_dir if git_dir.is_absolute() else checkout / git_dir


def archived_state_prs(checkout: Path) -> set[int]:
    """PR numbers whose archived `<git-dir>/pr-loop/state*.json` implies a missing summary.

    The live `state.json` is excluded: a loop running right now has not failed to
    reach Step 5, and reporting it as an orphan flags the PR being worked on. So
    are the statuses that finish without a comment on purpose.
    """
    loop_dir = _git_dir(checkout) / "pr-loop"
    if not loop_dir.is_dir():
        return set()
    found: set[int] = set()
    for path in loop_dir.glob("state*.json"):
        if path.name == "state.json":
            continue
        try:
            state = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(state, dict):
            continue
        if state.get("status") in _NO_COMMENT_STATUSES:
            continue
        pr = state.get("pr_number")
        if isinstance(pr, int):
            found.add(pr)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument(
        "--checkout",
        type=Path,
        help=(
            "local clone to cross-check for <git-dir>/pr-loop archives; warns about "
            "PRs the loop ran on that never posted a summary"
        ),
    )
    args = parser.parse_args()

    # A failing or absent gh leaves the PR set unknown, not empty. Emitting no
    # rows on stdout would read downstream as "the loop ran nowhere".
    try:
        hits, seen, partial = scan_repo(args.owner, args.repo)
    except subprocess.CalledProcessError as e:
        print(
            f"find_loop_prs: cannot scan {args.owner}/{args.repo}\nstderr: {e.stderr}",
            file=sys.stderr,
        )
        return 2
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError) as e:
        print(
            f"find_loop_prs: cannot scan {args.owner}/{args.repo}\n{type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return 2

    for pr in hits:
        print(f"{args.owner},{args.repo},{pr}")
    print(
        f"find_loop_prs: {len(hits)} of {len(seen)} merged PR(s) carry the summary marker",
        file=sys.stderr,
    )

    if args.checkout:
        # A run that died before Step 5 leaves state behind but posts no summary,
        # so the marker scan cannot see it. Warn rather than emit a row: archives
        # are gitignored and machine-local, so rows drawn from them would differ
        # per checkout. The scan can only speak for PRs it read: one that is not
        # merged was never queried, and a partly-read one may hide its marker in
        # what was missed, so neither counts as evidence.
        orphans = sorted((archived_state_prs(args.checkout) & set(seen)) - set(hits) - set(partial))
        if orphans:
            listed = ",".join(str(pr) for pr in orphans)
            print(
                f"find_loop_prs: {len(orphans)} PR(s) have loop state in "
                f"{args.checkout} but no summary comment: {listed}\n"
                "Those runs did not reach Step 5. Not emitted as rows.",
                file=sys.stderr,
            )

    if partial:
        # Some of a PR's comments could not be read, so its marker may be in the
        # part that was missed and the row set is short. Exiting 0 here would let
        # the documented append pipeline, which consumes stdout only, treat a
        # partial scan as complete.
        listed = ",".join(str(pr) for pr in partial)
        print(
            f"find_loop_prs: {len(partial)} PR(s) were only partly read "
            f"(more than {_COMMENT_PAGE} comments, or a comment the token "
            f"cannot resolve): {listed}\n"
            "The row set above may be short. Re-check those PRs by hand.",
            file=sys.stderr,
        )
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
