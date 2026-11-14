#!/usr/bin/env python3
"""project fetched comments for comments-phase and completion decisions."""

from __future__ import annotations

from typing import Any


def _content(rows: list[Any], *, review: bool = False) -> dict[str, tuple[str, ...]] | None:
    projected: dict[str, tuple[str, ...]] = {}
    for row in rows:
        if not isinstance(row, dict):
            return None
        comment_id = row.get("id")
        body = row.get("body")
        if (
            not isinstance(comment_id, str)
            or not comment_id
            or "body" not in row
            or (body is not None and not isinstance(body, str))
            or comment_id in projected
        ):
            return None
        normalized_body = body or ""
        if review:
            state = row.get("state")
            if not isinstance(state, str):
                return None
            projected[comment_id] = (normalized_body, state)
        else:
            projected[comment_id] = (normalized_body,)
    return projected


def _comment_projection(snapshot: Any) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict) or snapshot.get("fetch_error", object()) is not None:
        return None
    for field in ("issue_comments", "review_comments", "reviews", "review_threads"):
        if not isinstance(snapshot.get(field), list):
            return None

    issue_comments = _content(snapshot["issue_comments"])
    review_comments = _content(snapshot["review_comments"])
    reviews = _content(snapshot["reviews"], review=True)
    if issue_comments is None or review_comments is None or reviews is None:
        return None
    reply_review_ids = {
        ("review", row["id"])
        for row in snapshot["reviews"]
        if row.get("loop_reply_artifact") is True and reviews[row["id"]] == ("", "COMMENTED")
    }

    general: dict[tuple[str, str], tuple[str, ...]] = {
        ("issue_comment", comment_id): value for comment_id, value in issue_comments.items()
    }
    general.update({("review", comment_id): value for comment_id, value in reviews.items()})

    threads: dict[str, dict[str, Any]] = {}
    for thread in snapshot["review_threads"]:
        if not isinstance(thread, dict):
            return None
        root_id = thread.get("root_comment_id")
        is_resolved = thread.get("is_resolved")
        has_reply = thread.get("has_reply")
        replies = thread.get("replies")
        root_comment = thread.get("root_comment")
        if (
            not isinstance(root_id, str)
            or not root_id
            or type(is_resolved) is not bool
            or type(has_reply) is not bool
            or not isinstance(replies, list)
            or not isinstance(root_comment, dict)
            or root_comment.get("id") != root_id
            or root_id in threads
        ):
            return None
        content = _content([root_comment, *replies])
        if content is None:
            return None
        threads[root_id] = {
            "resolved": is_resolved,
            "required": not is_resolved or not has_reply,
            "content": content,
        }
    return {"general": general, "threads": threads, "reply_review_ids": reply_review_ids}


def _new_or_edited(before: dict[Any, Any], after: dict[Any, Any]) -> bool:
    return any(before.get(identity) != value for identity, value in after.items())


def _discussion_changes(
    before: dict[str, Any] | None, after: dict[str, Any]
) -> tuple[set[str], bool]:
    if before is None:
        return set(), True

    changed_roots: set[str] = set()
    for root_id, thread in after["threads"].items():
        previous = before["threads"].get(root_id)
        if previous is None:
            changed_roots.add(root_id)
            continue
        if _new_or_edited(previous["content"], thread["content"]):
            changed_roots.add(root_id)
            continue
        if previous["resolved"] and not thread["resolved"]:
            changed_roots.add(root_id)

    general_changed = any(
        before["general"].get(identity) != value
        for identity, value in after["general"].items()
        if identity in before["general"] or identity not in after["reply_review_ids"]
    )
    return changed_roots, bool(changed_roots) or general_changed


def _reviewed_comments(state: dict[str, Any]) -> dict[str, Any] | None:
    history = state.get("history")
    if not isinstance(history, list) or not history or not isinstance(history[-1], dict):
        return None
    if "human_comments" not in history[-1]:
        return None
    return _comment_projection(history[-1]["human_comments"])


def _disposition_roots(
    before: dict[str, Any] | None,
    after: dict[str, Any],
    handled: set[str],
    *,
    code_changed: bool = False,
) -> set[str]:
    required = {root_id for root_id, thread in after["threads"].items() if thread["required"]}
    changed, _ = _discussion_changes(before, after)
    needed = required if before is None else (required - handled) | changed
    if code_changed:
        needed |= handled & set(after["threads"])
    return needed
