"""discussion snapshots detect semantic feedback changes."""

from __future__ import annotations

import copy

import pytest
from comment_context import _comment_projection, _discussion_changes, _disposition_roots


def comment(comment_id: str, body: str, author: str = "reviewer") -> dict[str, object]:
    return {
        "id": comment_id,
        "body": body,
        "author": author,
        "created_at": "2026-09-10T00:00:00Z",
        "updated_at": "2026-09-10T00:00:00Z",
        "file": "scripts/example.py",
        "line": 10,
    }


def thread(
    root_id: str = "root-1",
    *,
    body: str = "root body",
    replies: list[dict[str, object]] | None = None,
    resolved: bool = False,
    has_reply: bool | None = None,
) -> dict[str, object]:
    reply_rows = replies if replies is not None else [comment("reply-1", "first reply")]
    return {
        "root_comment_id": root_id,
        "root_comment": comment(root_id, body),
        "replies": reply_rows,
        "is_resolved": resolved,
        "has_reply": bool(reply_rows) if has_reply is None else has_reply,
        "comment_ids": [root_id, *(row["id"] for row in reply_rows)],
    }


def envelope() -> dict[str, object]:
    return {
        "fetch_error": None,
        "fetched_at": "2026-09-10T00:00:00Z",
        "issue_comments": [comment("issue-1", "issue body")],
        "review_comments": [
            comment("root-1", "root body"),
            comment("reply-1", "first reply"),
        ],
        "reviews": [
            {
                **comment("review-1", "review body"),
                "state": "COMMENTED",
            }
        ],
        "review_threads": [thread()],
    }


def projected(snapshot: dict[str, object]) -> dict[str, object]:
    result = _comment_projection(snapshot)
    assert result is not None
    return result


@pytest.mark.parametrize(
    ("change", "expected_roots", "start_resolved"),
    [
        (
            lambda value: value["review_threads"].append(thread("root-2", replies=[])),
            {"root-2"},
            False,
        ),
        (
            lambda value: value["review_threads"][0]["root_comment"].update(body="edited"),
            {"root-1"},
            False,
        ),
        (
            lambda value: value["review_threads"][0]["replies"][0].update(body="edited"),
            {"root-1"},
            False,
        ),
        (
            lambda value: value["review_threads"][0]["replies"].append(
                comment("reply-2", "new reply")
            ),
            {"root-1"},
            False,
        ),
        (
            lambda value: value["issue_comments"].append(comment("issue-2", "new issue")),
            set(),
            False,
        ),
        (lambda value: value["issue_comments"][0].update(body="edited issue"), set(), False),
        (
            lambda value: value["reviews"].append(
                {**comment("review-2", "new review"), "state": "APPROVED"}
            ),
            set(),
            False,
        ),
        (lambda value: value["reviews"][0].update(body="edited review"), set(), False),
        (
            lambda value: value["reviews"][0].update(state="CHANGES_REQUESTED"),
            set(),
            False,
        ),
        (
            lambda value: value["review_threads"][0].update(is_resolved=False),
            {"root-1"},
            True,
        ),
    ],
    ids=[
        "new-root",
        "edited-root",
        "edited-existing-reply",
        "new-reply",
        "new-issue",
        "edited-issue",
        "new-review",
        "edited-review",
        "review-state",
        "reopened-thread",
    ],
)
def test_new_or_edited_feedback_changes_discussion(change, expected_roots, start_resolved):
    before_snapshot = envelope()
    if start_resolved:
        before_snapshot["review_threads"][0]["is_resolved"] = True
    after_snapshot = copy.deepcopy(before_snapshot)
    change(after_snapshot)

    roots, changed = _discussion_changes(projected(before_snapshot), projected(after_snapshot))

    assert roots == expected_roots
    assert changed is True


@pytest.mark.parametrize(
    ("author", "body"),
    [
        ("reviewer", "ordinary follow-up"),
        ("Copilot", "automated follow-up"),
        ("coderabbitai[bot]", "automated follow-up"),
        ("github-actions[bot]", "automated follow-up"),
        ("human-account", "robot: this still needs work"),
    ],
)
def test_thread_followup_detection_does_not_filter_by_author_or_body_prefix(author, body):
    before_snapshot = envelope()
    after_snapshot = copy.deepcopy(before_snapshot)
    after_snapshot["review_threads"][0]["replies"].append(comment(f"reply-{author}", body, author))

    assert _discussion_changes(projected(before_snapshot), projected(after_snapshot)) == (
        {"root-1"},
        True,
    )


def test_transport_metadata_line_movement_and_order_do_not_change_discussion():
    first = comment("reply-1", "first reply")
    second = comment("reply-2", "second reply")
    before_snapshot = envelope()
    before_snapshot["review_threads"] = [thread(replies=[first, second])]
    after_snapshot = copy.deepcopy(before_snapshot)
    after_snapshot["fetched_at"] = "2026-09-11T00:00:00Z"
    current_thread = after_snapshot["review_threads"][0]
    current_thread["comment_ids"] = ["reply-2", "root-1", "reply-1"]
    current_thread["root_comment"].update(line=99, updated_at="2026-09-11T00:00:00Z")
    current_thread["replies"].reverse()
    current_thread["replies"][0].update(line=88, updated_at="2026-09-11T00:00:00Z")
    after_snapshot["issue_comments"].reverse()
    after_snapshot["reviews"].reverse()

    assert _discussion_changes(projected(before_snapshot), projected(after_snapshot)) == (
        set(),
        False,
    )


def test_resolution_only_does_not_change_discussion():
    before_snapshot = envelope()
    after_snapshot = copy.deepcopy(before_snapshot)
    after_snapshot["review_threads"][0]["is_resolved"] = True

    assert _discussion_changes(projected(before_snapshot), projected(after_snapshot)) == (
        set(),
        False,
    )


def test_deletion_only_does_not_change_discussion():
    before_snapshot = envelope()
    after_snapshot = copy.deepcopy(before_snapshot)
    after_snapshot["review_threads"] = []
    after_snapshot["issue_comments"] = []
    after_snapshot["reviews"] = []

    assert _discussion_changes(projected(before_snapshot), projected(after_snapshot)) == (
        set(),
        False,
    )


def test_legacy_thread_without_replies_is_not_a_complete_snapshot():
    snapshot = envelope()
    del snapshot["review_threads"][0]["replies"]

    assert _comment_projection(snapshot) is None


def test_absent_baseline_requires_a_full_review_without_inventing_changed_roots():
    assert _discussion_changes(None, projected(envelope())) == (set(), True)


def test_handled_unchanged_root_is_redispositioned_only_after_code_changes():
    snapshot = projected(envelope())

    assert _disposition_roots(snapshot, snapshot, {"root-1"}) == set()
    assert _disposition_roots(snapshot, snapshot, {"root-1"}, code_changed=True) == {"root-1"}
