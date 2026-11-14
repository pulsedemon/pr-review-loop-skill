"""iteration and comment completion decisions."""

from __future__ import annotations

import copy
import io
import json

import pytest
from check_exit_conditions import decide, main
from pr_loop_state import StateValidationError


def comment(comment_id: str, body: str = "feedback") -> dict[str, object]:
    return {"id": comment_id, "body": body, "author": "reviewer"}


def thread(
    root: str = "1",
    *,
    body: str = "root feedback",
    resolved: bool = False,
    replied: bool = False,
    replies: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    reply_rows = (
        replies if replies is not None else ([comment(f"{root}-reply", "reply")] if replied else [])
    )
    return {
        "root_comment_id": root,
        "root_comment": comment(root, body),
        "replies": reply_rows,
        "is_resolved": resolved,
        "has_reply": replied or bool(reply_rows),
    }


def comments(*, threads=(), issues=(), reviews=(), error=None) -> dict[str, object]:
    return {
        "fetch_error": error,
        "issue_comments": list(issues),
        "review_comments": [],
        "reviews": list(reviews),
        "review_threads": list(threads),
    }


def review(
    review_id: str = "review-1", body: str = "review body", state: str = "COMMENTED"
) -> dict[str, object]:
    return {"id": review_id, "body": body, "state": state, "author": "reviewer"}


def reply_artifact() -> dict[str, object]:
    return {**review("reply-review", body=""), "loop_reply_artifact": True}


def receipt(root: str) -> dict[str, str]:
    return {
        "id": root,
        "source": "review_comment",
        "disposition": "addressed",
        "replied_at": "2026-09-10T00:00:00Z",
    }


def reviewed_state(iteration=1, *, baseline=None, ledger=()):
    return {
        "iteration": iteration,
        "max_iterations": 15,
        "approvers_required_list": ["tests"],
        "comment_ledger": list(ledger),
        "history": [
            {
                "iteration": iteration,
                "head_sha_before": "reviewed-head",
                "head_sha_after": "reviewed-head",
                "reviewers_completed": ["tests"],
                "reviewer_errors": [],
                "human_comments": comments() if baseline is None else baseline,
                "adversary": {
                    "reviewer": "adversary",
                    "verdict": "approve",
                    "findings": [],
                    "evidence": {"files_read": ["scripts/check_exit_conditions.py"]},
                },
            }
        ],
    }


def completion(*, baseline=None, current=None, handled=(), iteration=1):
    return decide(
        {
            "phase": "completion",
            "iteration": iteration,
            "comments": comments() if current is None else current,
            "current_head": "reviewed-head",
            "remote_head": "reviewed-head",
        },
        reviewed_state(
            iteration,
            baseline=comments() if baseline is None else baseline,
            ledger=[receipt(root) for root in handled],
        ),
    )


@pytest.mark.parametrize(
    ("phase", "completed", "iteration", "expected"),
    [
        ("entry", 0, None, None),
        ("entry", 14, None, None),
        ("entry", 15, None, "MAX_ITERATIONS"),
        ("edit", 13, 14, None),
        ("edit", 14, 15, "MAX_ITERATIONS"),
    ],
)
def test_iteration_boundary(phase, completed, iteration, expected):
    result = decide(
        {"phase": phase, "iteration": iteration},
        {"iteration": completed, "max_iterations": 15},
    )
    assert result["terminal_status"] == expected


@pytest.mark.parametrize("phase", ["edit", "completion"])
def test_stale_iteration_cannot_bypass_persisted_budget(phase):
    with pytest.raises(StateValidationError, match="persisted completed count"):
        decide({"phase": phase, "iteration": 1}, {"iteration": 15, "max_iterations": 15})


def test_final_fetch_failure_prevents_success():
    assert completion(current=comments(error="offline"))["terminal_status"] == "REVIEW_INCOMPLETE"


def test_missing_thread_metadata_prevents_success():
    assert completion(current=comments(threads=[{}]))["terminal_status"] == "REVIEW_INCOMPLETE"


def test_failed_prior_disposition_prevents_success():
    snapshot = comments(threads=[thread()])
    result = completion(baseline=snapshot, current=copy.deepcopy(snapshot))
    assert result["terminal_status"] == "REVIEW_INCOMPLETE"
    assert result["reason"] == "required replies remain unhandled"


def test_new_root_requires_full_panel():
    result = completion(current=comments(threads=[thread()]))
    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is True


def test_new_root_at_limit_stops():
    result = completion(current=comments(threads=[thread()]), iteration=15)
    assert result["terminal_status"] == "MAX_ITERATIONS"


def test_final_iteration_can_complete():
    result = completion(iteration=15)
    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is False


def test_unchanged_unresolved_thread_does_not_restart_after_handling():
    snapshot = comments(threads=[thread()])
    result = completion(
        baseline=snapshot,
        current=copy.deepcopy(snapshot),
        handled=["1"],
    )
    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is False


@pytest.mark.parametrize("iteration", [1, 15])
def test_reply_artifact_after_handled_root_does_not_restart_completion(iteration):
    before = comments(threads=[thread()])
    after = copy.deepcopy(before)
    after["review_threads"][0]["has_reply"] = True
    after["reviews"] = [reply_artifact()]
    original_before = copy.deepcopy(before)
    original_after = copy.deepcopy(after)

    result = completion(
        baseline=before,
        current=after,
        handled=["1"],
        iteration=iteration,
    )

    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is False
    assert before == original_before
    assert after == original_after


@pytest.mark.parametrize("completed", [1, 14])
def test_reply_artifact_after_handled_root_does_not_restart_comments_phase(completed):
    before = comments(threads=[thread()])
    after = copy.deepcopy(before)
    after["review_threads"][0]["has_reply"] = True
    after["reviews"] = [reply_artifact()]
    state = reviewed_state(completed, baseline=before, ledger=[receipt("1")])

    result = decide({"phase": "comments", "comments": after}, state)

    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is False
    assert result["disposition_root_ids"] == []


def test_resolved_unanswered_thread_requires_handling():
    snapshot = comments(threads=[thread(resolved=True)])
    result = completion(baseline=snapshot, current=copy.deepcopy(snapshot))
    assert result["terminal_status"] == "REVIEW_INCOMPLETE"


def test_resolved_answered_thread_needs_no_reply():
    snapshot = comments(threads=[thread(resolved=True, replied=True)])
    result = completion(baseline=snapshot, current=copy.deepcopy(snapshot))
    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is False


def test_initially_required_root_needs_ledger_after_resolution():
    before = comments(threads=[thread()])
    after = comments(threads=[thread(resolved=True, replied=True)])
    result = completion(baseline=before, current=after)
    assert result["terminal_status"] == "REVIEW_INCOMPLETE"


def test_handled_root_with_late_objection_restarts_full_panel():
    before = comments(threads=[thread(replied=True)])
    after = copy.deepcopy(before)
    after["review_threads"][0]["replies"].append(comment("late-reply", "late objection"))

    result = completion(baseline=before, current=after, handled=["1"])

    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is True


def test_legacy_history_without_comment_context_cannot_complete():
    state = reviewed_state()
    del state["history"][0]["human_comments"]

    result = decide(
        {
            "phase": "completion",
            "iteration": 1,
            "comments": comments(),
            "current_head": "reviewed-head",
            "remote_head": "reviewed-head",
        },
        state,
    )

    assert result["terminal_status"] == "REVIEW_INCOMPLETE"
    assert result["reason"] == "missing reviewed comments"


def test_comments_phase_without_legacy_context_redispositions_handled_required_root():
    state = reviewed_state(iteration=0)
    state["history"] = []
    state["comment_ledger"] = [receipt("1")]

    result = decide(
        {"phase": "comments", "comments": comments(threads=[thread()])},
        state,
    )

    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is True
    assert result["disposition_root_ids"] == ["1"]


def test_comments_phase_refuses_entry_after_the_iteration_budget_is_exhausted():
    state = reviewed_state(iteration=15, baseline=comments())

    result = decide({"phase": "comments", "comments": comments()}, state)

    assert result["terminal_status"] == "MAX_ITERATIONS"


@pytest.mark.parametrize(
    "new_review",
    [
        review(body=""),
        {**review(body=""), "loop_reply_artifact": "true"},
        {**review(body="objection"), "loop_reply_artifact": True},
        {**review(body=" "), "loop_reply_artifact": True},
        {**review(body="", state="APPROVED"), "loop_reply_artifact": True},
        {**review(body="", state="CHANGES_REQUESTED"), "loop_reply_artifact": True},
        {**review(body="", state="DISMISSED"), "loop_reply_artifact": True},
    ],
    ids=[
        "unannotated-empty-commented",
        "string-annotation",
        "annotated-objection",
        "annotated-whitespace",
        "annotated-approved",
        "annotated-changes-requested",
        "annotated-dismissed",
    ],
)
@pytest.mark.parametrize("iteration", [1, 15])
def test_non_artifact_new_review_restarts_panel(new_review, iteration):
    result = completion(
        baseline=comments(),
        current=comments(reviews=[new_review]),
        iteration=iteration,
    )

    if iteration == 15:
        assert result["terminal_status"] == "MAX_ITERATIONS"
    else:
        assert result["terminal_status"] is None
        assert result["continue_full_panel"] is True


@pytest.mark.parametrize(
    ("before_review", "after_review"),
    [
        (review("reply-review", body="substantive"), reply_artifact()),
        (review("reply-review", body="", state="APPROVED"), reply_artifact()),
        (reply_artifact(), review("reply-review", body="substantive")),
        (reply_artifact(), review("reply-review", body="", state="CHANGES_REQUESTED")),
    ],
    ids=[
        "substantive-to-artifact",
        "approved-to-artifact",
        "artifact-to-substantive",
        "artifact-to-changes-requested",
    ],
)
@pytest.mark.parametrize("iteration", [1, 15])
def test_review_identity_transition_restarts_panel(before_review, after_review, iteration):
    result = completion(
        baseline=comments(reviews=[before_review]),
        current=comments(reviews=[after_review]),
        iteration=iteration,
    )

    if iteration == 15:
        assert result["terminal_status"] == "MAX_ITERATIONS"
    else:
        assert result["terminal_status"] is None
        assert result["continue_full_panel"] is True


@pytest.mark.parametrize("author", ["copilot[bot]", "coderabbitai[bot]", "review-model"])
@pytest.mark.parametrize("iteration", [1, 15])
def test_inline_objection_alongside_reply_artifact_restarts_panel(author, iteration):
    before = comments(threads=[thread(replied=True)])
    after = copy.deepcopy(before)
    after["reviews"] = [reply_artifact()]
    after["review_threads"][0]["replies"].append(
        {**comment("late-objection", "ordinary objection"), "author": author}
    )
    result = completion(
        baseline=before,
        current=after,
        handled=["1"],
        iteration=iteration,
    )

    if iteration == 15:
        assert result["terminal_status"] == "MAX_ITERATIONS"
    else:
        assert result["terminal_status"] is None
        assert result["continue_full_panel"] is True


@pytest.mark.parametrize("author", ["copilot[bot]", "coderabbitai[bot]", "review-model"])
def test_comments_phase_selects_root_for_objection_alongside_reply_artifact(author):
    before = comments(threads=[thread(replied=True)])
    after = copy.deepcopy(before)
    after["reviews"] = [reply_artifact()]
    after["review_threads"][0]["replies"].append(
        {**comment("late-objection", "ordinary objection"), "author": author}
    )
    state = reviewed_state(1, baseline=before, ledger=[receipt("1")])

    result = decide({"phase": "comments", "comments": after}, state)

    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is True
    assert result["disposition_root_ids"] == ["1"]


@pytest.mark.parametrize("iteration", [1, 15])
def test_reply_artifact_without_review_history_requires_full_panel(iteration):
    result = decide(
        {"phase": "comments", "comments": comments(reviews=[reply_artifact()])},
        {"iteration": iteration - 1, "max_iterations": 15},
    )

    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is True


def changed_feedback(source: str) -> tuple[dict[str, object], dict[str, object]]:
    before = comments(
        threads=[thread(resolved=True, replied=True)],
        issues=[comment("issue-1", "old issue")],
        reviews=[review()],
    )
    after = copy.deepcopy(before)
    if source == "root":
        after["review_threads"][0]["root_comment"]["body"] = "edited root"
    elif source == "reply":
        after["review_threads"][0]["replies"][0]["body"] = "edited reply"
    elif source == "reopen":
        after["review_threads"][0]["is_resolved"] = False
    elif source == "issue":
        after["issue_comments"][0]["body"] = "edited issue"
    elif source == "review":
        after["reviews"][0]["body"] = "edited review"
    else:
        after["reviews"][0]["state"] = "CHANGES_REQUESTED"
    return before, after


@pytest.mark.parametrize("source", ["root", "reply", "reopen", "issue", "review", "review-state"])
def test_each_feedback_source_runs_full_panel_before_the_limit(source):
    before, after = changed_feedback(source)
    result = completion(baseline=before, current=after, handled=["1"], iteration=14)

    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is True


@pytest.mark.parametrize("source", ["root", "reply", "reopen", "issue", "review", "review-state"])
def test_each_feedback_source_stops_at_the_completion_limit(source):
    before, after = changed_feedback(source)
    result = completion(baseline=before, current=after, handled=["1"], iteration=15)

    assert result["terminal_status"] == "MAX_ITERATIONS"


@pytest.mark.parametrize("source", ["root", "reply", "reopen", "issue", "review", "review-state"])
def test_comments_entry_at_last_iteration_still_selects_full_panel(source):
    before, after = changed_feedback(source)
    state = reviewed_state(iteration=14, baseline=before, ledger=[receipt("1")])

    result = decide({"phase": "comments", "comments": after}, state)

    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is True


@pytest.mark.parametrize("phase", ["entry", "edit", "completion"])
def test_cli_rejects_missing_budget(phase, tmp_path, monkeypatch, capsys):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"iteration": 0}))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"phase": phase})))
    assert main(["--state", str(state)]) == 2
    assert "max_iterations" in capsys.readouterr().err


def test_completion_cli_returns_decision(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state.json"
    state.write_text(json.dumps(reviewed_state()))
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "phase": "completion",
                    "iteration": 1,
                    "comments": comments(error="offline"),
                    "current_head": "reviewed-head",
                    "remote_head": "reviewed-head",
                }
            )
        ),
    )
    assert main(["--state", str(state)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["terminal_status"] == "REVIEW_INCOMPLETE"
    assert result["reason"] == "incomplete comment content"


@pytest.mark.parametrize(
    "entry",
    [
        {"id": "1"},
        {
            "id": "1",
            "source": "issue_comment",
            "disposition": "addressed",
            "replied_at": "2026-09-10T00:00:00Z",
        },
        {
            "id": "1",
            "source": "review_comment",
            "disposition": "unknown",
            "replied_at": "2026-09-10T00:00:00Z",
        },
        {
            "id": "1",
            "source": "review_comment",
            "disposition": "addressed",
            "replied_at": "2026-09-10X00:00+00:00",
        },
        {
            "id": "1",
            "source": "review_comment",
            "disposition": "deferred",
            "replied_at": "2026-09-10T00:00:00Z",
        },
    ],
)
def test_malformed_ledger_entry_is_not_proof_of_handling(entry):
    snapshot = comments(threads=[thread()])
    state = reviewed_state(baseline=snapshot)
    state["comment_ledger"] = [entry]

    with pytest.raises(StateValidationError, match="comment_ledger"):
        decide(
            {
                "phase": "completion",
                "iteration": 1,
                "comments": copy.deepcopy(snapshot),
                "current_head": "reviewed-head",
                "remote_head": "reviewed-head",
            },
            state,
        )
