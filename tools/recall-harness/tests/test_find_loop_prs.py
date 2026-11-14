"""Tests for find_loop_prs: paging, the truncation guard, and archive detection.

`gh` is stubbed throughout — the module's whole job is turning GraphQL pages into
manifest rows, and that mapping is what these pin.
"""

import json
import pathlib
import subprocess
import sys
from unittest.mock import patch

import find_loop_prs  # type: ignore[import-not-found]  # noqa: E402  — sibling module via conftest.py
import pytest


def _page(nodes, *, cursor=None):
    return {
        "data": {
            "repository": {
                "pullRequests": {
                    "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor},
                    "nodes": nodes,
                }
            }
        }
    }


def _node(number, bodies, *, total=None):
    return {
        "number": number,
        "comments": {
            "totalCount": total if total is not None else len(bodies),
            "nodes": [{"body": b} for b in bodies],
        },
    }


def _gh(*payloads):
    """Stub subprocess.run for `gh` only, returning each payload in turn.

    Other commands fall through to the real one: archived_state_prs shells out to
    `git rev-parse --git-dir`, and swallowing that would test the wrong thing.
    """
    calls = [subprocess.CompletedProcess([], 0, json.dumps(p), "") for p in payloads]
    real = subprocess.run

    def run(cmd, *a, **k):
        if cmd and cmd[0] == "gh":
            return calls.pop(0)
        return real(cmd, *a, **k)

    return run


def test_scan_repo_pages_until_exhausted_and_sorts_hits():
    pages = _gh(
        _page([_node(9, [find_loop_prs.SUMMARY_MARKER]), _node(2, ["chatter"])], cursor="c1"),
        _page([_node(4, ["x", find_loop_prs.SUMMARY_MARKER])]),
    )
    with patch.object(find_loop_prs.subprocess, "run", pages):
        hits, seen, partial = find_loop_prs.scan_repo("o", "r")
    assert hits == [4, 9]
    assert seen == [9, 2, 4]
    assert partial == []


def test_scan_repo_reports_a_pr_whose_comments_overflow_the_page():
    """Only the first page of comments is read, so a marker past it is missed.
    The PR is reported rather than counted as a clean miss."""
    over = find_loop_prs._COMMENT_PAGE + 1
    with patch.object(
        find_loop_prs.subprocess, "run", _gh(_page([_node(5, ["chatter"], total=over)]))
    ):
        hits, _, partial = find_loop_prs.scan_repo("o", "r")
    assert hits == []
    assert partial == [5]


def test_main_exits_3_when_a_scan_was_truncated(capsys):
    """A short row set must not exit 0: the documented append pipeline reads
    stdout only, so the exit code is what stops it looking complete."""
    over = find_loop_prs._COMMENT_PAGE + 1
    nodes = [_node(5, ["chatter"], total=over), _node(6, [find_loop_prs.SUMMARY_MARKER])]
    with (
        patch.object(find_loop_prs.subprocess, "run", _gh(_page(nodes))),
        patch.object(sys, "argv", ["find_loop_prs.py", "o", "r"]),
    ):
        code = find_loop_prs.main()
    out = capsys.readouterr()
    assert code == 3
    assert out.out.splitlines() == ["o,r,6"]
    assert "5" in out.err


def test_main_does_not_call_a_truncated_pr_an_orphan(tmp_path, capsys):
    """A truncated PR's marker may sit past the page that was read, so it is not
    evidence the run ended before Step 5. The cross-check also has to run before
    the truncation exit, or a short scan skips it entirely."""
    loop = tmp_path / ".git" / "pr-loop"
    loop.mkdir(parents=True)
    (loop / "state.pr5.done.json").write_text(json.dumps({"pr_number": 5}))
    (loop / "state.pr8.done.json").write_text(json.dumps({"pr_number": 8}))
    over = find_loop_prs._COMMENT_PAGE + 1
    nodes = [
        _node(5, ["chatter"], total=over),
        _node(8, ["no marker here"]),
        _node(9, [find_loop_prs.SUMMARY_MARKER]),
    ]
    with (
        patch.object(find_loop_prs.subprocess, "run", _gh(_page(nodes))),
        patch.object(sys, "argv", ["find_loop_prs.py", "o", "r", "--checkout", str(tmp_path)]),
    ):
        code = find_loop_prs.main()
    err = capsys.readouterr().err
    assert code == 3
    assert "but no summary comment: 8" in err
    assert "comment: 5" not in err


def test_scan_repo_counts_an_unresolvable_comment_as_partly_read():
    """A nulled node may be the summary itself, which is the same short-row-set
    situation as an overflowing comment page, so it gets the same treatment."""
    payload = _page([_node(5, ["chatter"])])
    payload["data"]["repository"]["pullRequests"]["nodes"][0]["comments"]["nodes"].append(None)
    with patch.object(find_loop_prs.subprocess, "run", _gh(payload)):
        hits, _, partial = find_loop_prs.scan_repo("o", "r")
    assert hits == []
    assert partial == [5]


def test_main_only_calls_a_scanned_pr_an_orphan(tmp_path, capsys):
    """scan_repo queries merged PRs only, so an archive for one that is open or
    closed-unmerged was never looked at and cannot be called a failed run."""
    loop = tmp_path / ".git" / "pr-loop"
    loop.mkdir(parents=True)
    (loop / "state.pr7.done.json").write_text(json.dumps({"pr_number": 7}))
    (loop / "state.pr8.done.json").write_text(json.dumps({"pr_number": 8}))
    with (
        patch.object(find_loop_prs.subprocess, "run", _gh(_page([_node(8, ["no marker"])]))),
        patch.object(sys, "argv", ["find_loop_prs.py", "o", "r", "--checkout", str(tmp_path)]),
    ):
        code = find_loop_prs.main()
    err = capsys.readouterr().err
    assert code == 0
    assert "but no summary comment: 8" in err
    assert "comment: 7" not in err


def test_scan_repo_tolerates_a_null_comment_node():
    """GraphQL nulls a node the viewer cannot resolve without erroring. The null
    goes first: after the marker, any() short-circuits and never reaches it."""
    payload = _page([_node(7, [find_loop_prs.SUMMARY_MARKER])])
    payload["data"]["repository"]["pullRequests"]["nodes"][0]["comments"]["nodes"].insert(0, None)
    with patch.object(find_loop_prs.subprocess, "run", _gh(payload)):
        hits, _, _ = find_loop_prs.scan_repo("o", "r")
    assert hits == [7]


@pytest.mark.parametrize(
    ("name", "payload", "expected"),
    [
        ("state.pr12.done.json", {"pr_number": 12}, {12}),
        ("state.pr13.archived.json", {"pr_number": "13"}, set()),
        ("state.pr14.done.json", {"no_pr": 1}, set()),
    ],
)
def test_archived_state_prs_keeps_only_integer_pr_numbers(tmp_path, name, payload, expected):
    loop = tmp_path / ".git" / "pr-loop"
    loop.mkdir(parents=True)
    (loop / name).write_text(json.dumps(payload))
    assert find_loop_prs.archived_state_prs(tmp_path) == expected


def test_archived_state_prs_skips_the_live_state_file(tmp_path):
    """A loop running right now has not failed to reach Step 5; reporting it as
    an orphan flags the PR being worked on."""
    loop = tmp_path / ".git" / "pr-loop"
    loop.mkdir(parents=True)
    (loop / "state.json").write_text(json.dumps({"pr_number": 99}))
    (loop / "state.pr12.done.json").write_text(json.dumps({"pr_number": 12}))
    assert find_loop_prs.archived_state_prs(tmp_path) == {12}


@pytest.mark.parametrize("status", ["dry_run_complete", "setup_error", "review_incomplete"])
def test_archived_state_prs_skips_statuses_that_post_no_comment(tmp_path, status):
    loop = tmp_path / ".git" / "pr-loop"
    loop.mkdir(parents=True)
    (loop / "state.pr12.done.json").write_text(json.dumps({"pr_number": 12, "status": status}))
    (loop / "state.pr13.done.json").write_text(json.dumps({"pr_number": 13, "status": "running"}))
    assert find_loop_prs.archived_state_prs(tmp_path) == {13}


def test_archived_state_prs_skips_a_non_object_state_file(tmp_path):
    loop = tmp_path / ".git" / "pr-loop"
    loop.mkdir(parents=True)
    (loop / "state.pr12.done.json").write_text(json.dumps(["not", "an", "object"]))
    (loop / "state.pr13.done.json").write_text(json.dumps({"pr_number": 13}))
    assert find_loop_prs.archived_state_prs(tmp_path) == {13}


def test_archived_state_prs_skips_unreadable_files(tmp_path):
    loop = tmp_path / ".git" / "pr-loop"
    loop.mkdir(parents=True)
    (loop / "state.pr12.done.json").write_text("{not json")
    (loop / "state.pr13.done.json").write_text(json.dumps({"pr_number": 13}))
    assert find_loop_prs.archived_state_prs(tmp_path) == {13}


def test_archived_state_prs_follows_a_worktree_git_pointer(tmp_path):
    """In a worktree `.git` is a file pointing at the real git dir, and the loop
    writes state there. Assuming a directory skipped the check silently."""
    main = tmp_path / "main"
    main.mkdir()
    run = lambda *a: subprocess.run(a, cwd=main, check=True, capture_output=True)  # noqa: E731
    run("git", "init", "-q", "-b", "main", ".")
    run(
        "git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init", "--allow-empty"
    )
    checkout = tmp_path / "wt"
    run("git", "worktree", "add", "-q", "--detach", str(checkout))

    git_dir = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert not (checkout / ".git").is_dir(), "worktree .git should be a pointer file"
    loop = pathlib.Path(git_dir) / "pr-loop"
    loop.mkdir(parents=True)
    (loop / "state.pr42.done.json").write_text(json.dumps({"pr_number": 42}))

    assert find_loop_prs.archived_state_prs(checkout) == {42}


def test_archived_state_prs_returns_empty_outside_a_git_repo(tmp_path):
    assert find_loop_prs.archived_state_prs(tmp_path) == set()


def test_archived_state_prs_returns_empty_without_a_loop_dir(tmp_path):
    assert find_loop_prs.archived_state_prs(tmp_path) == set()


@pytest.mark.parametrize(
    "error",
    [
        subprocess.CalledProcessError(1, "gh", "", "rate limited"),
        FileNotFoundError("gh"),
    ],
)
def test_main_exits_2_and_emits_no_rows_when_the_scan_fails(capsys, error):
    """An unknown PR set must not print as an empty one: downstream that reads
    as 'the loop ran nowhere'."""

    def boom(*a, **k):
        raise error

    with (
        patch.object(find_loop_prs.subprocess, "run", boom),
        patch.object(sys, "argv", ["find_loop_prs.py", "o", "r"]),
    ):
        code = find_loop_prs.main()
    out = capsys.readouterr()
    assert code == 2
    assert out.out == ""
    assert "cannot scan" in out.err
