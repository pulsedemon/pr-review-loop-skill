"""required reviews must complete before the public completion gate can approve."""

import copy
import io
import json

import pytest
from check_exit_conditions import _review_completion_reason, decide, main
from pr_loop_state import APPROVER_LIST


def empty_comments():
    return {
        "fetch_error": None,
        "issue_comments": [],
        "review_comments": [],
        "reviews": [],
        "review_threads": [],
    }


def reviewed_state():
    return {
        "iteration": 1,
        "max_iterations": 15,
        "comment_ledger": [],
        "approvers_required_list": ["tests", "security"],
        "history": [
            {
                "iteration": 1,
                "head_sha_before": "reviewed-head",
                "head_sha_after": "reviewed-head",
                "reviewers_completed": ["tests", "security"],
                "reviewer_errors": [],
                "human_comments": empty_comments(),
                "adversary": {
                    "reviewer": "adversary",
                    "verdict": "approve",
                    "findings": [],
                    "evidence": {"files_read": ["scripts/check_exit_conditions.py"]},
                },
            }
        ],
    }


def completion_request():
    return {
        "phase": "completion",
        "iteration": 1,
        "comments": empty_comments(),
        "current_head": "reviewed-head",
        "remote_head": "reviewed-head",
    }


def test_complete_required_subset_can_finish():
    result = decide(completion_request(), reviewed_state())
    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is False


@pytest.mark.parametrize(
    ("present", "review_comments"),
    [
        pytest.param(False, None, id="missing"),
        pytest.param(True, None, id="null"),
        pytest.param(True, {}, id="nonlist"),
        pytest.param(True, ["not-a-comment"], id="scalar-row"),
        pytest.param(True, [{"id": "review-1"}], id="row-missing-body"),
    ],
)
def test_public_completion_rejects_malformed_review_comment_collection(present, review_comments):
    request = completion_request()
    if present:
        request["comments"]["review_comments"] = review_comments
    else:
        del request["comments"]["review_comments"]

    result = decide(request, reviewed_state())

    assert result["terminal_status"] == "REVIEW_INCOMPLETE"
    assert result["reason"] == "incomplete comment content"


@pytest.mark.parametrize("receipt", [None, [], ["tests"], ["tests", "tests"]])
def test_missing_or_duplicate_receipts_cannot_replace_a_required_review(receipt):
    state = reviewed_state()
    if receipt is None:
        del state["history"][0]["reviewers_completed"]
    else:
        state["history"][0]["reviewers_completed"] = receipt
    assert _review_completion_reason(state) == "required panel reviews did not complete"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"iteration": 0}, "missing current review record"),
        ({"head_sha_after": "edited-head"}, "current head requires review"),
        (
            {"reviewer_errors": [{"reviewer": "tests", "error": "invalid JSON"}]},
            "required panel review failed",
        ),
        ({"adversary_error": "offline"}, "final adversary review failed"),
        ({"adversary": None}, "missing or invalid final adversary response"),
        ({"adversary_shallow_giveup": True}, "final adversary review did not complete"),
    ],
)
def test_stale_or_failed_reviews_cannot_finish(change, reason):
    state = reviewed_state()
    if "adversary_error" in change:
        del state["history"][0]["adversary"]
    state["history"][0].update(copy.deepcopy(change))
    assert _review_completion_reason(state) == reason


@pytest.mark.parametrize("legacy_count", [None, 0, 2])
def test_shallow_final_review_cannot_finish_at_any_legacy_count(legacy_count):
    state = reviewed_state()
    if legacy_count is not None:
        state["shallow_approval_adversary_runs"] = legacy_count
    del state["history"][0]["adversary"]["evidence"]
    assert _review_completion_reason(state) == "final adversary approval lacks read evidence"


@pytest.mark.parametrize("files_read", [[""], [" \t\n "], ["", " "]])
def test_blank_read_evidence_cannot_complete_final_approval(files_read):
    state = reviewed_state()
    state["history"][0]["adversary"]["evidence"]["files_read"] = files_read
    result = decide(completion_request(), state)
    assert result["terminal_status"] == "REVIEW_INCOMPLETE"
    assert result["reason"] == "final adversary approval lacks read evidence"


def test_one_named_file_satisfies_final_approval_read_evidence():
    state = reviewed_state()
    state["history"][0]["adversary"]["evidence"]["files_read"] = [
        " ",
        "scripts/check_exit_conditions.py",
        "",
    ]
    result = decide(completion_request(), state)
    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is False


def test_wrong_adversary_identity_cannot_finish():
    state = reviewed_state()
    state["history"][0]["adversary"]["reviewer"] = "security"
    assert _review_completion_reason(state) == "final adversary identity mismatch"


@pytest.mark.parametrize("verdict", ["comment", "request_changes"])
@pytest.mark.parametrize("with_evidence", [False, True])
def test_empty_adversary_response_requires_approval(verdict, with_evidence):
    state = reviewed_state()
    adversary = state["history"][0]["adversary"]
    adversary["verdict"] = verdict
    if not with_evidence:
        del adversary["evidence"]
    result = decide(completion_request(), state)
    assert result["terminal_status"] == "REVIEW_INCOMPLETE"
    assert result["reason"] == "final adversary returned no findings without approval"


@pytest.mark.parametrize(
    ("severity", "scope"),
    [("suggestion", "in_scope"), ("nit", "in_scope"), ("suggestion", "out_of_scope")],
)
def test_nonblocking_adversary_findings_preserve_completion(severity, scope):
    state = reviewed_state()
    state["history"][0]["adversary"].update(
        verdict="comment",
        findings=[
            {
                "severity": severity,
                "scope": scope,
                "summary": "nonblocking follow-up",
                "file": "README.md",
                "line": 1,
                "detail": "optional wording improvement",
            }
        ],
    )
    del state["history"][0]["adversary"]["evidence"]
    result = decide(completion_request(), state)
    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is False


@pytest.mark.parametrize("failure", ["missing_panel", "failed_adversary", "shallow_adversary"])
def test_public_completion_gate_rejects_incomplete_reviews(failure):
    state = reviewed_state()
    entry = state["history"][0]
    if failure == "missing_panel":
        entry["reviewers_completed"] = ["tests"]
    elif failure == "failed_adversary":
        del entry["adversary"]
        entry["adversary_error"] = "offline"
    else:
        del entry["adversary"]["evidence"]
    assert decide(completion_request(), state)["terminal_status"] == "REVIEW_INCOMPLETE"


@pytest.mark.parametrize("changed", ["current_head", "remote_head"])
def test_public_completion_rejects_a_head_changed_during_review(changed):
    request = completion_request()
    request[changed] = "external-head"
    assert decide(request, reviewed_state())["terminal_status"] == "EXTERNAL_PUSH"


def test_public_completion_succeeds_at_the_last_iteration():
    state = reviewed_state()
    state["iteration"] = state["max_iterations"]
    state["history"][0]["iteration"] = state["iteration"]
    request = completion_request()
    request["iteration"] = state["iteration"]
    result = decide(request, state)
    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is False


def test_forced_full_sweep_receipts_can_complete_an_initial_partial_selection():
    state = reviewed_state()
    entry = state["history"][0]
    entry["panel_selection"] = {
        "mode": "delta_gated",
        "ran": ["tests"],
        "skipped": ["security"],
        "gate_relevant": ["tests"],
        "gate_fail_open": [],
        "open_blocker_carryover": [],
    }
    entry["forced_full_sweep"] = True
    result = decide(completion_request(), state)
    assert result["terminal_status"] is None
    assert result["continue_full_panel"] is False


def test_absent_required_subset_requires_the_full_panel():
    state = reviewed_state()
    del state["approvers_required_list"]
    assert decide(completion_request(), state)["terminal_status"] == "REVIEW_INCOMPLETE"
    state["history"][0]["reviewers_completed"] = APPROVER_LIST.copy()
    assert decide(completion_request(), state)["continue_full_panel"] is False


@pytest.mark.parametrize("missing", ["current_head", "remote_head"])
@pytest.mark.parametrize("complete_panel", [True, False])
def test_missing_fresh_head_is_a_cli_setup_error(
    missing, complete_panel, tmp_path, monkeypatch, capsys
):
    state = reviewed_state()
    if not complete_panel:
        state["history"][0]["reviewers_completed"] = ["tests"]
        state["history"][0]["reviewer_errors"] = [{"reviewer": "security", "error": "timed out"}]
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state))
    request = completion_request()
    del request[missing]
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(request)))
    assert main(["--state", str(state_path)]) == 2
    assert f"completion requires {missing}" in capsys.readouterr().err


def test_unreadable_reviewer_schema_is_a_cli_setup_error(tmp_path, monkeypatch, capsys):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(reviewed_state()))
    monkeypatch.setattr("validate_reviewer_output.SCHEMA_PATH", tmp_path / "missing-schema.json")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(completion_request())))
    assert main(["--state", str(state_path)]) == 2
    assert "invalid or unreadable reviewer schema" in capsys.readouterr().err
