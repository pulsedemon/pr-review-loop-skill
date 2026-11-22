"""Tests for scripts/pr_loop_state.py."""

from __future__ import annotations

import copy
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from personas_manifest import load_manifest  # type: ignore[import-not-found]
from pr_loop_state import (  # type: ignore[import-not-found]
    ALLOWED_STATE_STATUSES,
    APPROVER_LIST,
    StateValidationError,
    _main,
    append_history_entry,
    apply_pr_scope_update,
    build_initial_state,
    build_iteration_metric,
    build_terminal_metric,
    load_state,
    resume_decision,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Distinguishes "key absent" from "key present but empty" in the parametrize tables.
_MISSING = object()


@pytest.mark.parametrize("completed", [0, 1])
def test_resume_decision_starts_after_completed_iterations(completed: int) -> None:
    state = {
        "initial_head_sha": "initial",
        "iteration": completed,
        "max_iterations": 2,
        "history": [{"iteration": 1, "head_sha_after": "latest"}] if completed else [],
    }
    expected_head = "latest" if completed else "initial"

    decision = resume_decision(state=state, current_head=expected_head, remote_head=expected_head)

    assert decision["terminal_status"] is None
    assert decision["next_iteration"] == completed + 1


@pytest.mark.parametrize(
    ("history", "current", "remote", "dirty"),
    [
        ([], "unrecorded", "initial", False),
        ([], "initial", "moved", False),
        ([], "initial", "", False),
        ([], "initial", "initial", True),
        (
            [{"iteration": 1, "head_sha_before": "initial", "head_sha_after": "latest"}],
            "initial",
            "latest",
            False,
        ),
        ([{"iteration": 1, "head_sha_after": "latest"}], "unrecorded", "latest", False),
        ([{"iteration": 1, "head_sha_after": "latest"}], "latest", "moved", False),
    ],
)
def test_resume_decision_refuses_unowned_checkout(
    history: list[dict], current: str, remote: str, dirty: bool
) -> None:
    decision = resume_decision(
        state={
            "initial_head_sha": "initial",
            "iteration": len(history),
            "max_iterations": 3,
            "history": history,
        },
        current_head=current,
        remote_head=remote,
        dirty=dirty,
    )

    assert decision["terminal_status"] == "EXTERNAL_PUSH"
    assert decision["next_iteration"] is None


@pytest.mark.parametrize("abort", [False, True])
def test_resume_decision_honors_scope_abort_before_exhausted_budget(abort: bool) -> None:
    decision = resume_decision(
        state={
            "iteration": 1,
            "max_iterations": 1,
            "history": [{"iteration": 1, "head_sha_after": "latest"}],
            "pr_scope": {"user_decision": "abort" if abort else "continue"},
        },
        current_head="latest",
        remote_head="latest",
    )

    assert decision["terminal_status"] == ("SCOPE_SPLIT_RECOMMENDED" if abort else "MAX_ITERATIONS")
    assert decision["next_iteration"] is None


@pytest.mark.parametrize(
    "updates",
    [
        {"iteration": 1},
        {"history": [{}]},
        {"iteration": 1, "history": [{"iteration": 2, "head_sha_after": "initial"}]},
        {"iteration": 1, "history": [{"iteration": True, "head_sha_after": "initial"}]},
        {"iteration": 1, "history": [{"iteration": 1}]},
        {"max_iterations": 0},
        {"initial_head_sha": ""},
    ],
)
def test_resume_decision_rejects_inconsistent_state(updates: dict) -> None:
    state = {"iteration": 0, "max_iterations": 2, "initial_head_sha": "initial", "history": []}
    state.update(updates)

    with pytest.raises(StateValidationError):
        resume_decision(state=state, current_head="initial", remote_head="initial")


def test_main_resume_decision_reads_without_writing(tmp_path, capsys) -> None:
    path = tmp_path / "state.json"
    original = '{"iteration": 0, "max_iterations": 2, "initial_head_sha": "head", "history": []}\n'
    path.write_text(original)

    assert (
        _main(
            [
                "resume-decision",
                "--state",
                str(path),
                "--current-head",
                "head",
                "--remote-head",
                "head",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["next_iteration"] == 1
    assert path.read_text() == original


def test_main_resume_decision_reports_malformed_state(tmp_path, capsys) -> None:
    path = tmp_path / "state.json"
    path.write_text("{broken")

    assert (
        _main(
            [
                "resume-decision",
                "--state",
                str(path),
                "--current-head",
                "head",
                "--remote-head",
                "head",
            ]
        )
        == 2
    )
    assert "failed to parse state.json" in capsys.readouterr().err


def test_approver_list_matches_manifest() -> None:
    # APPROVER_LIST in pr_loop_state.py duplicates reviewers/personas.yaml `panel:`
    # (kept inline to avoid a runtime pyyaml dependency). This pins the two together.
    manifest = load_manifest(_REPO_ROOT / "reviewers" / "personas.yaml")
    assert APPROVER_LIST == [persona.name for persona in manifest.panel]


def test_build_initial_state_uses_expected_defaults() -> None:
    meta = {
        "number": 42,
        "title": "Test PR",
        "url": "https://github.com/o/r/pull/42",
        "headRefName": "feature",
        "baseRefName": "main",
        "headRefOid": "deadbeef",
        "author": {"login": "alice"},
    }

    state = build_initial_state(
        owner="o",
        repo="r",
        max_iterations=15,
        started_at="2026-05-20T02:01:51Z",
        meta=meta,
    )

    assert state["pr_url"] == meta["url"]
    assert state["pr_number"] == 42
    assert state["owner"] == "o"
    assert state["repo"] == "r"
    assert state["initial_head_sha"] == "deadbeef"
    assert state["pr_author"] == "alice"
    assert state["iteration"] == 0
    assert state["status"] == "running"
    assert state["history"] == []
    assert state["pr_scope_mode"] == "auto"
    assert state["max_new_loc"] == 1000
    assert state["approvers_required"] == "all"
    assert state["approvers_required_list"] == [
        "correctness",
        "tests",
        "security",
        "performance",
        "readability",
        "yagni",
        "requirements",
        "comments",
        "error_handling",
        "type_design",
        "blind_spots",
    ]
    assert state["suggestion_promotion_threshold"] == 0
    assert state["adversary_promotion"] is False
    assert state["adversary_solo_promotion"] is False
    assert state["adversary_panel_visibility"] == "full"
    assert state["shallow_adversary_runs"] == 0
    assert "shallow_approval_adversary_runs" not in state


def test_build_initial_state_copies_default_approver_list() -> None:
    meta = {
        "number": 42,
        "title": "Test PR",
        "url": "https://github.com/o/r/pull/42",
        "headRefName": "feature",
        "baseRefName": "main",
        "headRefOid": "deadbeef",
        "author": {"login": "alice"},
    }

    first = build_initial_state(
        owner="o",
        repo="r",
        max_iterations=15,
        started_at="2026-05-20T02:01:51Z",
        meta=meta,
    )
    second = build_initial_state(
        owner="o",
        repo="r",
        max_iterations=15,
        started_at="2026-05-20T02:01:51Z",
        meta=meta,
    )

    first["approvers_required_list"].append("extra-reviewer")

    assert "extra-reviewer" not in second["approvers_required_list"]


def test_build_initial_state_rejects_non_positive_max_iterations() -> None:
    meta = {
        "number": 42,
        "title": "Test PR",
        "url": "https://github.com/o/r/pull/42",
        "headRefName": "feature",
        "baseRefName": "main",
        "headRefOid": "deadbeef",
        "author": {"login": "alice"},
    }

    with pytest.raises(ValueError, match="max_iterations must be >= 1"):
        build_initial_state(
            owner="o",
            repo="r",
            max_iterations=0,
            started_at="2026-05-20T02:01:51Z",
            meta=meta,
        )


def test_build_initial_state_rejects_missing_meta_key() -> None:
    meta = {
        "number": 42,
        "title": "Test PR",
        "headRefName": "feature",
        "baseRefName": "main",
        "headRefOid": "deadbeef",
        "author": {"login": "alice"},
    }

    with pytest.raises(StateValidationError, match="missing required key.*url"):
        build_initial_state(
            owner="o",
            repo="r",
            max_iterations=15,
            started_at="2026-05-20T02:01:51Z",
            meta=meta,
        )


def test_main_init_state_returns_2_on_malformed_meta_json(capsys) -> None:
    rc = _main(
        [
            "init-state",
            "--owner",
            "o",
            "--repo",
            "r",
            "--max-iterations",
            "5",
            "--started-at",
            "2026-05-20T02:01:51Z",
            "--meta-json",
            "{broken",
        ]
    )

    assert rc == 2
    err = capsys.readouterr().err
    assert "pr_loop_state: failed to parse meta JSON" in err


def test_main_init_state_returns_2_on_incomplete_meta_json(capsys) -> None:
    rc = _main(
        [
            "init-state",
            "--owner",
            "o",
            "--repo",
            "r",
            "--max-iterations",
            "5",
            "--started-at",
            "2026-05-20T02:01:51Z",
            "--meta-json",
            '{"number":42}',
        ]
    )

    assert rc == 2
    err = capsys.readouterr().err
    assert "pr_loop_state: meta JSON missing required key(s)" in err


def test_build_iteration_metric_counts_findings_and_promotions() -> None:
    state = {
        "iteration": 2,
        "shallow_adversary_runs": 1,
        "history": [
            {
                "ci_status": "skipped",
                "findings": [
                    {
                        "severity": "blocker",
                        "scope": "in_scope",
                        "summary": "blocker",
                        "file": "a",
                        "line": 1,
                        "detail": "detail",
                    },
                    {
                        "severity": "suggestion",
                        "scope": "in_scope",
                        "summary": "suggestion",
                        "file": "b",
                        "line": 2,
                        "detail": "detail",
                    },
                    {
                        "severity": "nit",
                        "scope": "out_of_scope",
                        "summary": "nit",
                    },
                ],
                "demoted": [{"summary": "demoted"}],
                "shallow_review": ["tests"],
                "reviewer_errors": [{"reviewer": "security", "error": "bad json"}],
                "human_comments": {
                    "issue_comments": [{}],
                    "review_comments": [{}, {}],
                    "reviews": [{"body": ""}, {"body": "looks good"}],
                },
                "addressed": [
                    "legacy-string",
                    {"promotion_reason": "multi_source"},
                    {"promotion_reason": "adversary_endorsed"},
                    {"promotion_reason": "evidence_gated_solo_adversary"},
                ],
                "deferred": [
                    "legacy-string",
                    {"promotion_reason": "evidence_verification_failed"},
                ],
                "adversary": {"verdict": "approve", "findings": []},
                "model_routing": {
                    "delta_gate": {"tier": "cheap", "model": "haiku"},
                    "reviewer": {"tier": "standard", "model": "sonnet"},
                    "adversary": {"tier": "inherit"},
                },
            }
        ],
    }

    metric = build_iteration_metric(
        state=state,
        owner="o",
        repo="r",
        pr_number=9,
        timestamp="2026-05-20T02:04:14Z",
    )

    assert metric == {
        "kind": "iteration",
        "ts": "2026-05-20T02:04:14Z",
        "pr": "o/r#9",
        "iteration": 2,
        "ci_status": "skipped",
        "n_blockers": 1,
        "n_suggestions": 1,
        "n_nits": 1,
        "n_demoted": 1,
        "n_shallow": 1,
        "n_reviewer_errors": 1,
        "n_issue_comments": 1,
        "n_review_comments": 2,
        "n_reviews": 1,
        "promoted": {
            "multi_source": 1,
            "adversary_endorsed": 1,
            "evidence_gated_solo_adversary": 1,
        },
        "failed": {"evidence_verification": 1},
        "adversary_ran": True,
        "shallow_adversary_runs": 1,
        "models": {
            "delta_gate": "haiku",
            "reviewer": "sonnet",
            "adversary": "inherit",
        },
    }


def test_build_iteration_metric_models_empty_when_routing_absent() -> None:
    metric = build_iteration_metric(
        state={
            "iteration": 1,
            "history": [
                {
                    "ci_status": "skipped",
                    "findings": [],
                    "addressed": [],
                    "deferred": [],
                }
            ],
        },
        owner="o",
        repo="r",
        pr_number=9,
        timestamp="2026-05-20T02:04:14Z",
    )

    assert metric["models"] == {}


def test_build_iteration_metric_models_skip_malformed_phase_entries() -> None:
    metric = build_iteration_metric(
        state={
            "iteration": 1,
            "history": [
                {
                    "ci_status": "skipped",
                    "findings": [],
                    "addressed": [],
                    "deferred": [],
                    "model_routing": {
                        "reviewer": {"tier": "standard", "model": "sonnet"},
                        "adversary": "not-an-object",
                        "delta_gate": {"tier": "cheap"},
                    },
                }
            ],
        },
        owner="o",
        repo="r",
        pr_number=9,
        timestamp="2026-05-20T02:04:14Z",
    )

    assert metric["models"] == {"reviewer": "sonnet", "delta_gate": "cheap"}


def test_build_iteration_metric_rejects_non_dict_model_routing() -> None:
    with pytest.raises(ValueError, match="history\\[-1\\] field 'model_routing' must be an object"):
        build_iteration_metric(
            state={
                "iteration": 1,
                "history": [
                    {
                        "ci_status": "skipped",
                        "findings": [],
                        "addressed": [],
                        "deferred": [],
                        "model_routing": ["not", "an", "object"],
                    }
                ],
            },
            owner="o",
            repo="r",
            pr_number=9,
            timestamp="2026-05-20T02:04:14Z",
        )


def test_build_iteration_metric_requires_non_empty_history() -> None:
    with pytest.raises(ValueError, match="history\\[\\] is empty"):
        build_iteration_metric(
            state={"iteration": 2, "history": []},
            owner="o",
            repo="r",
            pr_number=9,
            timestamp="2026-05-20T02:04:14Z",
        )


def test_build_iteration_metric_treats_explicit_nulls_as_defaults() -> None:
    metric = build_iteration_metric(
        state={
            "iteration": 2,
            "shallow_adversary_runs": None,
            "history": [
                {
                    "ci_status": None,
                    "findings": [],
                    "addressed": [],
                    "deferred": [],
                }
            ],
        },
        owner="o",
        repo="r",
        pr_number=9,
        timestamp="2026-05-20T02:04:14Z",
    )

    assert metric["ci_status"] == "skipped"
    assert metric["shallow_adversary_runs"] == 0


def test_build_iteration_metric_treats_false_adversary_fields_as_absent() -> None:
    metric = build_iteration_metric(
        state={
            "iteration": 2,
            "history": [
                {
                    "ci_status": "skipped",
                    "findings": [],
                    "addressed": [],
                    "deferred": [],
                    "adversary": False,
                    "adversary_error": False,
                }
            ],
        },
        owner="o",
        repo="r",
        pr_number=9,
        timestamp="2026-05-20T02:04:14Z",
    )

    assert metric["adversary_ran"] is False


def test_build_iteration_metric_rejects_wrong_nested_types() -> None:
    with pytest.raises(ValueError, match="history\\[-1\\] field 'findings' must be a list"):
        build_iteration_metric(
            state={
                "iteration": 2,
                "history": [
                    {
                        "ci_status": "skipped",
                        "findings": {},
                        "addressed": [],
                        "deferred": [],
                    }
                ],
            },
            owner="o",
            repo="r",
            pr_number=9,
            timestamp="2026-05-20T02:04:14Z",
        )


def test_build_terminal_metric_computes_totals_and_wall_clock() -> None:
    state = {
        "owner": "o",
        "repo": "r",
        "pr_number": 9,
        "max_iterations": 15,
        "approvers_required": "all",
        "pr_scope_mode": "auto",
        "max_new_loc": 1000,
        "suggestion_promotion_threshold": 2,
        "adversary_promotion": True,
        "adversary_solo_promotion": True,
        "adversary_panel_visibility": "full",
        "approvers_required_list": ["correctness", "tests"],
        "iteration": 2,
        "loop_started_at": "2026-05-16T12:00:00Z",
        "history": [
            {
                "findings": [
                    {
                        "severity": "blocker",
                        "scope": "in_scope",
                        "summary": "blocker",
                        "file": "a",
                        "line": 1,
                        "detail": "detail",
                    }
                ],
                "addressed": [
                    {"promotion_reason": "multi_source"},
                    {"promotion_reason": "adversary_endorsed"},
                ],
                "deferred": [
                    {"promotion_reason": "evidence_verification_failed"},
                ],
                "demoted": [{"summary": "demoted"}],
                "shallow_review": ["tests"],
                "reviewer_errors": [{"reviewer": "security", "error": "bad json"}],
                "human_comments": {
                    "issue_comments": [{}],
                    "review_comments": [{}, {}],
                    "reviews": [{"body": ""}, {"body": "review body"}],
                },
            },
            {
                "findings": [
                    {
                        "severity": "suggestion",
                        "scope": "in_scope",
                        "summary": "suggestion",
                        "file": "b",
                        "line": 2,
                        "detail": "detail",
                    },
                    {"severity": "nit", "scope": "out_of_scope", "summary": "nit"},
                ],
                "addressed": [
                    {"promotion_reason": "multi_source"},
                    {"promotion_reason": "evidence_gated_solo_adversary"},
                ],
                "deferred": [],
                "demoted": [],
                "shallow_review": [],
                "reviewer_errors": [],
                "human_comments": {
                    "issue_comments": [],
                    "review_comments": [{}],
                    "reviews": [{"body": "another review"}],
                },
            },
        ],
    }

    metric = build_terminal_metric(
        state=state,
        terminal_status="SUCCESS",
        timestamp="2026-05-20T02:04:14Z",
        now=datetime(2026, 5, 20, 2, 4, 14, tzinfo=UTC),
    )

    assert metric == {
        "kind": "terminal",
        "ts": "2026-05-20T02:04:14Z",
        "pr": "o/r#9",
        "terminal_status": "SUCCESS",
        "iterations_completed": 2,
        "wall_clock_seconds": 309854,
        "knobs": {
            "max_iterations": 15,
            "approvers_required": "all",
            "pr_scope": "auto",
            "max_new_loc": 1000,
            "suggestion_promotion_threshold": 2,
            "adversary_promotion": True,
            "adversary_solo_promotion": True,
            "adversary_panel_visibility": "full",
        },
        "panel_size": 2,
        "totals": {
            "blockers": 1,
            "suggestions": 1,
            "nits": 1,
            "demoted": 1,
            "shallow_iterations": 1,
            "reviewer_errors": 1,
            "promoted_multi_source": 2,
            "promoted_adversary_endorsed": 1,
            "promoted_evidence_gated_solo_adversary": 1,
            "evidence_verification_failed": 1,
            "issue_comments_seen_total": 1,
            "review_comments_seen_total": 3,
            "reviews_seen_total": 2,
        },
    }


def test_build_terminal_metric_rejects_unknown_terminal_status() -> None:
    state = {"owner": "o", "repo": "r", "pr_number": 1, "iteration": 0, "history": []}
    with pytest.raises(StateValidationError, match="terminal status must be one of"):
        build_terminal_metric(
            state=state, terminal_status="SUCESS", timestamp="2026-09-10T00:00:00Z"
        )
    with pytest.raises(StateValidationError, match="terminal status must be one of"):
        build_terminal_metric(
            state=state, terminal_status="RUNNING", timestamp="2026-09-10T00:00:00Z"
        )


def test_build_terminal_metric_defaults_missing_iteration_and_started_at() -> None:
    metric = build_terminal_metric(
        state={
            "owner": "o",
            "repo": "r",
            "pr_number": 9,
            "max_iterations": 15,
            "history": [],
        },
        terminal_status="SETUP_ERROR",
        timestamp="2026-05-20T02:04:14Z",
        now=datetime(2026, 5, 20, 2, 4, 14, tzinfo=UTC),
    )

    assert metric["iterations_completed"] == 0
    assert metric["wall_clock_seconds"] == -1


def test_build_terminal_metric_treats_explicit_nulls_as_defaults() -> None:
    metric = build_terminal_metric(
        state={
            "owner": "o",
            "repo": "r",
            "pr_number": 9,
            "max_iterations": 15,
            "approvers_required": None,
            "pr_scope_mode": None,
            "max_new_loc": None,
            "suggestion_promotion_threshold": None,
            "adversary_promotion": None,
            "adversary_solo_promotion": None,
            "adversary_panel_visibility": None,
            "approvers_required_list": None,
            "history": [],
        },
        terminal_status="SETUP_ERROR",
        timestamp="2026-05-20T02:04:14Z",
        now=datetime(2026, 5, 20, 2, 4, 14, tzinfo=UTC),
    )

    assert metric["knobs"] == {
        "max_iterations": 15,
        "approvers_required": "all",
        "pr_scope": "auto",
        "max_new_loc": 1000,
        "suggestion_promotion_threshold": 2,
        "adversary_promotion": True,
        "adversary_solo_promotion": True,
        "adversary_panel_visibility": "full",
    }
    assert metric["panel_size"] == 0


def test_build_terminal_metric_preserves_false_boolean_knobs() -> None:
    metric = build_terminal_metric(
        state={
            "owner": "o",
            "repo": "r",
            "pr_number": 9,
            "max_iterations": 15,
            "adversary_promotion": False,
            "adversary_solo_promotion": False,
            "history": [],
        },
        terminal_status="SETUP_ERROR",
        timestamp="2026-05-20T02:04:14Z",
        now=datetime(2026, 5, 20, 2, 4, 14, tzinfo=UTC),
    )

    assert metric["knobs"]["adversary_promotion"] is False
    assert metric["knobs"]["adversary_solo_promotion"] is False


def test_build_terminal_metric_requires_pr_identity_fields() -> None:
    with pytest.raises(ValueError, match="state.json missing required field 'owner'"):
        build_terminal_metric(
            state={
                "repo": "r",
                "pr_number": 9,
                "max_iterations": 15,
                "history": [],
            },
            terminal_status="SETUP_ERROR",
            timestamp="2026-05-20T02:04:14Z",
            now=datetime(2026, 5, 20, 2, 4, 14, tzinfo=UTC),
        )


def test_build_terminal_metric_rejects_invalid_loop_started_at() -> None:
    with pytest.raises(ValueError, match="loop_started_at must be an ISO 8601 timestamp"):
        build_terminal_metric(
            state={
                "owner": "o",
                "repo": "r",
                "pr_number": 9,
                "max_iterations": 15,
                "loop_started_at": "not-a-date",
                "history": [],
            },
            terminal_status="SETUP_ERROR",
            timestamp="2026-05-20T02:04:14Z",
            now=datetime(2026, 5, 20, 2, 4, 14, tzinfo=UTC),
        )


def test_build_terminal_metric_rejects_timezone_less_loop_started_at() -> None:
    with pytest.raises(ValueError, match="must include a timezone offset or Z suffix"):
        build_terminal_metric(
            state={
                "owner": "o",
                "repo": "r",
                "pr_number": 9,
                "max_iterations": 15,
                "loop_started_at": "2026-05-20T02:04:14",
                "history": [],
            },
            terminal_status="SETUP_ERROR",
            timestamp="2026-05-20T02:04:14Z",
            now=datetime(2026, 5, 20, 2, 4, 14, tzinfo=UTC),
        )


def test_build_terminal_metric_requires_history_list() -> None:
    with pytest.raises(ValueError, match="state.json field 'history' must be a present list"):
        build_terminal_metric(
            state={
                "owner": "o",
                "repo": "r",
                "pr_number": 9,
                "max_iterations": 15,
                "history": {},
            },
            terminal_status="SETUP_ERROR",
            timestamp="2026-05-20T02:04:14Z",
            now=datetime(2026, 5, 20, 2, 4, 14, tzinfo=UTC),
        )


@pytest.mark.parametrize("state_kwargs", [{}, {"history": None}])
def test_build_terminal_metric_rejects_missing_or_null_history(
    state_kwargs: dict[str, object],
) -> None:
    """Missing/null history is structural corruption; the prior jq impl errored too."""
    with pytest.raises(ValueError, match="state.json field 'history' must be a present list"):
        build_terminal_metric(
            state={
                "owner": "o",
                "repo": "r",
                "pr_number": 9,
                "max_iterations": 15,
                **state_kwargs,
            },
            terminal_status="SETUP_ERROR",
            timestamp="2026-05-20T02:04:14Z",
            now=datetime(2026, 5, 20, 2, 4, 14, tzinfo=UTC),
        )


def test_build_terminal_metric_rejects_non_string_loop_started_at() -> None:
    with pytest.raises(ValueError, match="loop_started_at must be a string when present"):
        build_terminal_metric(
            state={
                "owner": "o",
                "repo": "r",
                "pr_number": 9,
                "max_iterations": 15,
                "loop_started_at": 123,
                "history": [],
            },
            terminal_status="SETUP_ERROR",
            timestamp="2026-05-20T02:04:14Z",
            now=datetime(2026, 5, 20, 2, 4, 14, tzinfo=UTC),
        )


def test_build_iteration_metric_rejects_bool_iteration() -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        build_iteration_metric(
            state={
                "iteration": True,
                "history": [
                    {
                        "ci_status": "skipped",
                        "findings": [],
                        "addressed": [],
                        "deferred": [],
                    }
                ],
            },
            owner="o",
            repo="r",
            pr_number=9,
            timestamp="2026-05-20T02:04:14Z",
        )


def test_build_terminal_metric_rejects_bad_approver_list_type() -> None:
    with pytest.raises(
        ValueError, match="state.json field 'approvers_required_list' must be a list"
    ):
        build_terminal_metric(
            state={
                "owner": "o",
                "repo": "r",
                "pr_number": 9,
                "max_iterations": 15,
                "iteration": 0,
                "approvers_required_list": {},
                "history": [],
            },
            terminal_status="SUCCESS",
            timestamp="2026-05-20T02:04:14Z",
            now=datetime(2026, 5, 20, 2, 4, 14, tzinfo=UTC),
        )


def test_load_state_wraps_malformed_json(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text("{broken\n", encoding="utf-8")

    with pytest.raises(ValueError, match="failed to parse state.json"):
        load_state(state_path)


def test_load_state_wraps_invalid_utf8(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_bytes(b'{"owner": "o", "repo": "r", "bad": "\\xff"}')

    with pytest.raises(ValueError, match="failed to parse state.json"):
        load_state(state_path)


def make_step_pr_scope(**updates: object) -> dict[str, object]:
    pr_scope: dict[str, object] = {
        "threshold": 1000,
        "new_loc_total": 1248,
        "per_file": [
            {
                "path": "scripts/pr_scope_step.py",
                "added": 100,
                "deleted": 0,
            }
        ],
        "excluded_paths": [],
        "verdict": "request_split",
        "summary": "Split the PR.",
        "splits": [
            {
                "name": "scope helper",
                "rationale": "Independent helper.",
                "files": [
                    {
                        "path": "scripts/pr_scope_step.py",
                        "hunks": ["L1-L20"],
                    }
                ],
                "estimated_new_loc": 100,
                "depends_on": [],
            }
        ],
        "remaining_in_original": ["scripts/pr_scope_step.py"],
        "user_decision": "abort",
    }
    pr_scope.update(updates)
    return pr_scope


def make_history_entry(**updates: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "head_sha_before": "abc123",
        "head_sha_after": "def456",
        "findings": [],
        "ci_status": "skipped",
        "panel_selection": {
            "mode": "full",
            "ran": [],
            "skipped": [],
            "gate_relevant": [],
            "gate_fail_open": [],
            "open_blocker_carryover": [],
        },
    }
    entry.update(updates)
    return entry


def test_apply_pr_scope_update_sets_pr_scope_and_status() -> None:
    state = {"status": "running", "history": [], "iteration": 0}

    updated = apply_pr_scope_update(
        state=state,
        pr_scope=make_step_pr_scope(),
        status="scope_split_recommended",
    )

    assert updated == {
        "status": "scope_split_recommended",
        "history": [],
        "iteration": 0,
        "pr_scope": make_step_pr_scope(),
    }
    assert state == {"status": "running", "history": [], "iteration": 0}


def test_apply_pr_scope_update_rejects_non_string_status() -> None:
    with pytest.raises(ValueError, match="status must be a string"):
        apply_pr_scope_update(
            state={"status": "running", "history": [], "iteration": 0},
            pr_scope=make_step_pr_scope(),
            status=123,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("status", ["", " ", "bogus"])
def test_apply_pr_scope_update_rejects_invalid_status(status: str) -> None:
    with pytest.raises(ValueError, match="status must be one of"):
        apply_pr_scope_update(
            state={"status": "running", "history": [], "iteration": 0},
            pr_scope=make_step_pr_scope(),
            status=status,
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"threshold": 0}, "pr_scope.threshold"),
        ({"new_loc_total": -1}, "pr_scope.new_loc_total"),
        ({"per_file": [{"path": "x", "added": 1}]}, "missing required field 'deleted'"),
        ({"excluded_paths": [False]}, "pr_scope.excluded_paths"),
        ({"verdict": "bogus"}, "pr_scope.verdict"),
        ({"summary": False}, "pr_scope.summary"),
        ({"verdict": "atomic", "summary": ""}, "non-empty string for atomic"),
        ({"verdict": "atomic", "summary": "   "}, "non-empty string for atomic"),
        ({"verdict": "request_split", "summary": ""}, "non-empty string for atomic"),
        ({"splits": [{"name": "x"}]}, "missing required field 'rationale'"),
        (
            {
                "splits": [
                    {
                        "name": "x",
                        "rationale": "r",
                        "files": [{"path": "x", "hunks": [False]}],
                        "estimated_new_loc": 1,
                    }
                ]
            },
            "hunks",
        ),
        (
            {
                "splits": [
                    {
                        "name": "x",
                        "rationale": "r",
                        "files": [{"path": "x", "hunks": []}],
                        "estimated_new_loc": 1,
                    }
                ]
            },
            "hunks",
        ),
        (
            {
                "splits": [
                    {
                        "name": "x",
                        "rationale": "r",
                        "files": ["x"],
                        "estimated_new_loc": 1,
                        "depends_on": [False],
                    }
                ]
            },
            "depends_on",
        ),
        ({"remaining_in_original": [False]}, "pr_scope.remaining_in_original"),
        ({"user_decision": "bogus"}, "pr_scope.user_decision"),
    ],
)
def test_apply_pr_scope_update_rejects_schema_invalid_pr_scope(
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        apply_pr_scope_update(
            state={"status": "running", "history": [], "iteration": 0},
            pr_scope=make_step_pr_scope(**updates),
        )


@pytest.mark.parametrize("verdict", ["atomic", "request_split"])
def test_apply_pr_scope_update_rejects_missing_summary_for_decisive_verdicts(
    verdict: str,
) -> None:
    pr_scope = make_step_pr_scope(verdict=verdict)
    del pr_scope["summary"]
    with pytest.raises(ValueError, match="non-empty string for atomic/request_split"):
        apply_pr_scope_update(
            state={"status": "running", "history": [], "iteration": 0},
            pr_scope=pr_scope,
        )


def test_append_history_entry_appends_and_increments_iteration() -> None:
    updated = append_history_entry(
        state={"status": "running", "iteration": 1, "history": []},
        entry=make_history_entry(),
    )

    assert updated["iteration"] == 2
    assert updated["history"] == [{**make_history_entry(), "iteration": 2}]


@pytest.mark.parametrize("completed", [[], ["tests"], _MISSING])
def test_append_history_entry_preserves_receipts_or_legacy_absence(completed):
    entry = make_history_entry()
    if completed is not _MISSING:
        entry["reviewers_completed"] = completed
    updated = append_history_entry(state={"iteration": 0, "history": []}, entry=entry)
    if completed is _MISSING:
        assert "reviewers_completed" not in updated["history"][0]
    else:
        assert updated["history"][0]["reviewers_completed"] == completed


@pytest.mark.parametrize("completed", [["tests", "tests"], ["unknown"], None])
def test_append_history_entry_rejects_invalid_receipts_without_mutating_state(completed):
    state = {"iteration": 0, "history": []}
    entry = make_history_entry(reviewers_completed=completed)
    original = json.dumps([state, entry], sort_keys=True)
    with pytest.raises(StateValidationError, match="reviewers_completed"):
        append_history_entry(state=state, entry=entry)
    assert json.dumps([state, entry], sort_keys=True) == original


def test_append_history_entry_rejects_non_string_status() -> None:
    with pytest.raises(ValueError, match="status must be a string"):
        append_history_entry(
            state={"status": "running", "iteration": 1, "history": []},
            entry=make_history_entry(),
            status={"bad": "status"},  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("status", ["", " ", "bogus"])
def test_append_history_entry_rejects_invalid_status(status: str) -> None:
    with pytest.raises(ValueError, match="status must be one of"):
        append_history_entry(
            state={"status": "running", "iteration": 1, "history": []},
            entry=make_history_entry(),
            status=status,
        )


def test_append_history_entry_rejects_mismatched_explicit_iteration() -> None:
    with pytest.raises(ValueError, match="history entry iteration must match next iteration"):
        append_history_entry(
            state={"status": "running", "iteration": 1, "history": []},
            entry=make_history_entry(iteration=5),
        )


def test_append_history_entry_rejects_missing_required_fields() -> None:
    with pytest.raises(ValueError, match="history entry missing required field"):
        append_history_entry(
            state={"status": "running", "iteration": 1, "history": []},
            entry={},
        )


def test_append_history_entry_rejects_missing_head_sha_after() -> None:
    with pytest.raises(ValueError, match="history entry missing required field 'head_sha_after'"):
        append_history_entry(
            state={"status": "running", "iteration": 1, "history": []},
            entry={
                "head_sha_before": "abc123",
                "findings": [],
                "ci_status": "skipped",
                "panel_selection": make_history_entry()["panel_selection"],
            },
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("head_sha_before", "", "head_sha_before must be a non-empty string"),
        ("head_sha_after", None, "head_sha_after must be a non-empty string"),
        ("findings", {}, "findings must be a list"),
        ("ci_status", "", "ci_status must be a non-empty string"),
        ("panel_selection", [], "panel_selection must be an object"),
    ],
)
def test_append_history_entry_rejects_malformed_required_field_types(
    field: str, value: object, message: str
) -> None:
    entry = make_history_entry(**{field: value})

    with pytest.raises(ValueError, match=message):
        append_history_entry(
            state={"status": "running", "iteration": 1, "history": []},
            entry=entry,
        )


def test_append_history_entry_rejects_invalid_ci_status_value() -> None:
    with pytest.raises(ValueError, match="ci_status must be one of"):
        append_history_entry(
            state={"status": "running", "iteration": 1, "history": []},
            entry=make_history_entry(ci_status="bogus"),
        )


@pytest.mark.parametrize(
    ("panel_selection", "message"),
    [
        (
            {"mode": "full", "ran": [], "skipped": []},
            "panel_selection missing required field 'gate_relevant'",
        ),
        (
            {
                "mode": "full",
                "ran": [],
                "skipped": [],
                "gate_relevant": [],
                "gate_fail_open": [],
                "open_blocker_carryover": [],
                "extra": [],
            },
            "panel_selection has unexpected field",
        ),
        (
            {
                "mode": "bogus",
                "ran": [],
                "skipped": [],
                "gate_relevant": [],
                "gate_fail_open": [],
                "open_blocker_carryover": [],
            },
            "panel_selection.mode must be one of",
        ),
        (
            {
                "mode": "full",
                "ran": [123],
                "skipped": [],
                "gate_relevant": [],
                "gate_fail_open": [],
                "open_blocker_carryover": [],
            },
            "panel_selection.ran must be a list of strings",
        ),
    ],
)
def test_append_history_entry_rejects_schema_invalid_panel_selection(
    panel_selection: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        append_history_entry(
            state={"status": "running", "iteration": 1, "history": []},
            entry=make_history_entry(panel_selection=panel_selection),
        )


def test_main_append_history_returns_updated_state_json(tmp_path, capsys) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"status":"running","history":[],"iteration":0}\n', encoding="utf-8")
    entry_json = (
        '{"head_sha_before":"abc123","head_sha_after":"def456","findings":[],"ci_status":"skipped",'
        '"panel_selection":{"mode":"full","ran":[],"skipped":[],"gate_relevant":[],'
        '"gate_fail_open":[],"open_blocker_carryover":[]}}'
    )

    rc = _main(
        [
            "append-history",
            "--state",
            str(state_path),
            "--entry-json",
            entry_json,
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert '"iteration":1' in out
    assert '"history":[{"ci_status":"skipped"' in out
    assert '"iteration":1' in state_path.read_text(encoding="utf-8")


def comment_snapshot(body: str = "review this") -> dict[str, object]:
    root = {"id": "root-1", "body": body, "author": "reviewer", "line": 9}
    return {
        "fetch_error": None,
        "fetched_at": "2026-09-10T00:00:00Z",
        "issue_comments": [],
        "review_comments": [copy.deepcopy(root)],
        "reviews": [],
        "review_threads": [
            {
                "root_comment_id": "root-1",
                "root_comment": root,
                "replies": [],
                "is_resolved": False,
                "has_reply": False,
                "comment_ids": ["root-1"],
            }
        ],
    }


def comment_receipt(
    root: str = "root-1",
    *,
    disposition: str = "addressed",
    replied_at: str = "2026-09-10T00:00:00Z",
) -> dict[str, str]:
    receipt = {
        "id": root,
        "source": "review_comment",
        "disposition": disposition,
        "replied_at": replied_at,
    }
    if disposition == "deferred":
        receipt["reason"] = "follow-up is outside this change"
    return receipt


def state_with_reviewed_comments() -> dict[str, object]:
    return {
        "iteration": 1,
        "history": [{"iteration": 1, "human_comments": comment_snapshot()}],
        "comment_ledger": [
            comment_receipt(),
            comment_receipt("other-root", replied_at="2026-09-09T00:00:00Z"),
        ],
    }


def history_with_comments(snapshot: dict[str, object], *, code_changed: bool = False):
    return make_history_entry(
        head_sha_before="abc123",
        head_sha_after="def456" if code_changed else "abc123",
        human_comments=snapshot,
    )


@pytest.mark.parametrize("updates", [None, []])
def test_changed_ledgered_root_requires_a_fresh_disposition_without_mutation(updates) -> None:
    state = state_with_reviewed_comments()
    current = comment_snapshot("late objection")
    entry = history_with_comments(current)
    original = copy.deepcopy((state, entry))

    with pytest.raises(StateValidationError, match="missing fresh comment dispositions: root-1"):
        append_history_entry(state=state, entry=entry, comment_updates=updates)

    assert (state, entry) == original


@pytest.mark.parametrize("body", ["review this", "late objection"])
def test_fresh_disposition_upserts_ledger_and_preserves_exact_snapshot(body) -> None:
    state = state_with_reviewed_comments()
    current = comment_snapshot(body)
    current["transport_marker"] = {"request": "second-fetch"}
    entry = history_with_comments(current)
    update = comment_receipt(
        disposition="deferred",
        replied_at="2026-09-11T00:00:00Z",
    )
    original = copy.deepcopy((state, entry))

    updated = append_history_entry(state=state, entry=entry, comment_updates=[update])

    assert updated["iteration"] == 2
    assert updated["history"][-1]["human_comments"] == current
    assert {item["id"]: item for item in updated["comment_ledger"]} == {
        "root-1": update,
        "other-root": comment_receipt("other-root", replied_at="2026-09-09T00:00:00Z"),
    }
    assert (state, entry) == original


def test_code_change_rechecks_unchanged_ledgered_root() -> None:
    state = state_with_reviewed_comments()
    entry = history_with_comments(comment_snapshot(), code_changed=True)

    with pytest.raises(StateValidationError, match="missing fresh comment dispositions: root-1"):
        append_history_entry(state=state, entry=entry)

    updated = append_history_entry(
        state=state,
        entry=entry,
        comment_updates=[comment_receipt(replied_at="2026-09-11T00:00:00Z")],
    )
    assert updated["iteration"] == 2
    assert updated["history"][-1]["human_comments"] == comment_snapshot()


@pytest.mark.parametrize("updates", [None, []])
def test_record_only_append_accepts_absent_or_empty_comment_updates(updates) -> None:
    updated = append_history_entry(
        state={"iteration": 0, "history": []},
        entry=make_history_entry(),
        comment_updates=updates,
    )

    assert updated["iteration"] == 1
    assert "human_comments" not in updated["history"][0]


@pytest.mark.parametrize("updates", [None, []])
def test_dry_run_snapshot_accepts_absent_or_empty_comment_updates(updates) -> None:
    updated = append_history_entry(
        state={"iteration": 0, "history": [], "dry_run": True},
        entry=history_with_comments(comment_snapshot()),
        comment_updates=updates,
    )

    assert updated["iteration"] == 1
    assert updated["history"][0]["human_comments"] == comment_snapshot()


@pytest.mark.parametrize(
    ("dry_run", "with_snapshot"),
    [(False, False), (True, False), (True, True)],
)
def test_main_append_input_rejects_updates_without_reviewed_comments_atomically(
    dry_run, with_snapshot, tmp_path, monkeypatch, capsys
) -> None:
    state = {"iteration": 0, "history": [], "dry_run": dry_run}
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state, separators=(",", ":")) + "\n", encoding="utf-8")
    original = state_path.read_bytes()
    entry = history_with_comments(comment_snapshot()) if with_snapshot else make_history_entry()
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"entry": entry, "comment_updates": [comment_receipt()]})),
    )

    assert _main(["append-history", "--state", str(state_path), "--input-json", "-"]) == 2
    assert (
        "comment updates require reviewed comments in a non-dry-run append"
        in capsys.readouterr().err
    )
    assert state_path.read_bytes() == original


@pytest.mark.parametrize(
    "review_comments",
    [
        pytest.param(_MISSING, id="missing"),
        pytest.param(None, id="nonlist"),
        pytest.param([{"id": "review-1"}], id="malformed-row"),
    ],
)
def test_main_append_input_rejects_malformed_review_comments_atomically(
    review_comments, tmp_path, monkeypatch, capsys
) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"iteration":0,"history":[]}\n', encoding="utf-8")
    original = state_path.read_bytes()
    snapshot = comment_snapshot()
    if review_comments is _MISSING:
        del snapshot["review_comments"]
    else:
        snapshot["review_comments"] = review_comments
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "entry": history_with_comments(snapshot),
                    "comment_updates": [comment_receipt()],
                }
            )
        ),
    )

    assert _main(["append-history", "--state", str(state_path), "--input-json", "-"]) == 2
    assert "cannot record incomplete reviewed comments" in capsys.readouterr().err
    assert state_path.read_bytes() == original


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (lambda entry: {"entry": entry}, "missing fresh comment dispositions"),
        (
            lambda entry: {"entry": entry, "comment_updates": [{"id": "root-1"}]},
            "invalid comment_ledger entry",
        ),
    ],
)
def test_main_append_input_rejects_missing_or_malformed_receipt_atomically(
    payload, message, tmp_path, monkeypatch, capsys
) -> None:
    state_path = tmp_path / "state.json"
    state = state_with_reviewed_comments()
    state_path.write_text(json.dumps(state, separators=(",", ":")) + "\n", encoding="utf-8")
    original = state_path.read_bytes()
    entry = history_with_comments(comment_snapshot("late objection"))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload(entry))))

    assert _main(["append-history", "--state", str(state_path), "--input-json", "-"]) == 2
    assert message in capsys.readouterr().err
    assert state_path.read_bytes() == original


def test_main_append_input_persists_snapshot_and_ledger_upsert_together(
    tmp_path, monkeypatch, capsys
) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state_with_reviewed_comments()) + "\n", encoding="utf-8")
    current = comment_snapshot("late objection")
    update = comment_receipt(replied_at="2026-09-11T00:00:00Z")
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "entry": history_with_comments(current),
                    "comment_updates": [update],
                }
            )
        ),
    )

    assert _main(["append-history", "--state", str(state_path), "--input-json", "-"]) == 0
    capsys.readouterr()
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["iteration"] == 2
    assert persisted["history"][-1]["human_comments"] == current
    assert {item["id"]: item for item in persisted["comment_ledger"]}["root-1"] == update


def test_append_history_entry_persists_ci_failed_checks():
    """CI_STUCK compares check names across iterations, so the names must survive
    the append. last_ci_status.json is overwritten per ci_wait.sh call and cannot
    answer what failed on the previous visit."""
    state = {"iteration": 0, "history": []}
    entry = {
        "head_sha_before": "a" * 40,
        "head_sha_after": "b" * 40,
        "findings": [],
        "ci_status": "failure",
        "ci_failed_checks": ["build", "lint"],
        "panel_selection": {
            "mode": "full",
            "ran": ["correctness"],
            "skipped": [],
            "gate_relevant": [],
            "gate_fail_open": [],
            "open_blocker_carryover": [],
        },
    }
    out = append_history_entry(state=state, entry=entry)
    assert out["history"][0]["ci_failed_checks"] == ["build", "lint"]


@pytest.mark.parametrize(
    ("checks", "message"),
    [
        (_MISSING, "ci_failed_checks must be a non-empty list"),
        ([], "ci_failed_checks must be a non-empty list"),
        ("build", "ci_failed_checks must be a non-empty list"),
        ([""], "every ci_failed_checks entry must be a non-empty string"),
        (["build", 1], "every ci_failed_checks entry must be a non-empty string"),
    ],
)
def test_append_history_entry_rejects_nameless_failure(checks: object, message: str) -> None:
    """A failure entry with no names is the CI_STUCK miss: §4d.1 walks back to the
    most recent failure entry, finds nothing recorded, and a permanently-red check
    keeps burning iterations."""
    entry = make_history_entry(ci_status="failure")
    if checks is not _MISSING:
        entry["ci_failed_checks"] = checks

    with pytest.raises(ValueError, match=message):
        append_history_entry(
            state={"status": "running", "iteration": 1, "history": []},
            entry=entry,
        )


@pytest.mark.parametrize("ci_status", ["skipped", "success", "timeout"])
def test_append_history_entry_allows_nameless_non_failure(ci_status: str) -> None:
    """Only a failure carries names. ci_wait.sh exit 2 maps timeout straight to
    CI_STUCK without recording any, so the constraint must not reach it."""
    updated = append_history_entry(
        state={"status": "running", "iteration": 1, "history": []},
        entry=make_history_entry(ci_status=ci_status),
    )

    assert "ci_failed_checks" not in updated["history"][0]


def test_main_append_history_rejects_nameless_failure(tmp_path, capsys) -> None:
    """§4i invokes the CLI, not the function. StateValidationError must surface as
    a clean exit 2, not a traceback."""
    state_path = tmp_path / "state.json"
    state_path.write_text('{"status":"running","history":[],"iteration":0}\n', encoding="utf-8")
    entry = make_history_entry(ci_status="failure")

    rc = _main(
        [
            "append-history",
            "--state",
            str(state_path),
            "--entry-json",
            json.dumps(entry),
        ]
    )

    assert rc == 2
    captured = capsys.readouterr()
    assert "ci_failed_checks must be a non-empty list" in captured.err
    assert "Traceback" not in captured.err
    assert '"history":[]' in state_path.read_text(encoding="utf-8").replace(" ", "")


@pytest.mark.parametrize(
    ("ci_status", "checks", "valid"),
    [
        ("failure", _MISSING, False),
        ("failure", [], False),
        ("failure", [""], False),
        ("failure", ["build"], True),
        ("skipped", _MISSING, True),
        ("success", ["build"], True),
    ],
)
def test_schema_couples_ci_failed_checks_to_failure(
    ci_status: str, checks: object, valid: bool
) -> None:
    """The helper's rule and the schema's if/then are maintained separately; this
    pins the schema half behaviorally rather than restating its JSON."""
    schema = json.loads((_REPO_ROOT / "templates" / "state.schema.json").read_text())
    entry = {**make_history_entry(ci_status=ci_status), "iteration": 1}
    if checks is not _MISSING:
        entry["ci_failed_checks"] = checks
    document = {
        "pr_url": "https://github.com/o/r/pull/1",
        "pr_number": 1,
        "owner": "o",
        "repo": "r",
        "base_branch": "main",
        "head_branch": "f",
        "iteration": 1,
        "max_iterations": 15,
        "status": "running",
        "history": [entry],
    }

    errors = list(Draft202012Validator(schema).iter_errors(document))

    assert (not errors) is valid, [error.message for error in errors]


@pytest.mark.parametrize(
    ("field", "value", "valid"),
    [
        ("head_sha_after", _MISSING, False),
        ("head_sha_after", "", False),
        ("head_sha_before", "", False),
        ("head_sha_after", "def456", True),
    ],
)
def test_schema_requires_non_empty_head_shas(field: str, value: object, valid: bool) -> None:
    """append_history_entry has always demanded both SHAs as non-empty strings while
    the schema left head_sha_after optional and unconstrained. §4h passes
    history[-1].head_sha_after to safe_push.sh as the expected remote head, and a
    missing one reads as fast-forwardable, re-pushing over a force-push that rewound
    the remote."""
    schema = json.loads((_REPO_ROOT / "templates" / "state.schema.json").read_text())
    entry = {**make_history_entry(), "iteration": 1}
    if value is _MISSING:
        del entry[field]
    else:
        entry[field] = value
    document = {
        "pr_url": "https://github.com/o/r/pull/1",
        "pr_number": 1,
        "owner": "o",
        "repo": "r",
        "base_branch": "main",
        "head_branch": "f",
        "iteration": 1,
        "max_iterations": 15,
        "status": "running",
        "history": [entry],
    }

    errors = list(Draft202012Validator(schema).iter_errors(document))

    assert (not errors) is valid, [error.message for error in errors]


@pytest.mark.parametrize(
    "record",
    [
        {"file": "src/a.py", "line": 10, "summary": "typo in a comment", "fixed_from": "nit"},
        {"summary": "unused import in an untouched file", "fixed_from": "suggestion"},
    ],
)
def test_schema_admits_fixed_suggestion_and_nit_records(record: dict) -> None:
    """A located and an unlocated fix record must each match exactly one
    addressed[] branch; a oneOf overlap with the promotion branch rejects them."""
    schema = json.loads((_REPO_ROOT / "templates" / "state.schema.json").read_text())
    entry = {**make_history_entry(), "iteration": 1, "addressed": [record]}
    document = {
        "pr_url": "https://github.com/o/r/pull/1",
        "pr_number": 1,
        "owner": "o",
        "repo": "r",
        "base_branch": "main",
        "head_branch": "f",
        "iteration": 1,
        "max_iterations": 15,
        "status": "running",
        "history": [entry],
    }

    errors = list(Draft202012Validator(schema).iter_errors(document))

    assert not errors, [error.message for error in errors]


def test_allowed_state_statuses_matches_schema_enum():
    """The helper keeps its own status allowlist independent of
    templates/state.schema.json. They drifted once: dry_run_complete was added to
    the schema, so the canonical contract accepted it while append_history_entry
    still raised."""
    schema_path = _REPO_ROOT / "templates" / "state.schema.json"
    schema = json.loads(schema_path.read_text())
    schema_statuses = set(schema["properties"]["status"]["enum"])
    assert ALLOWED_STATE_STATUSES == schema_statuses, (
        f"helper-only: {sorted(ALLOWED_STATE_STATUSES - schema_statuses)}, "
        f"schema-only: {sorted(schema_statuses - ALLOWED_STATE_STATUSES)}"
    )


def test_build_initial_state_persists_dry_run():
    """Resume re-parses invocation options; without a persisted mode a resumed
    dry run defaults back to false and continues into apply/commit/push."""
    meta = {
        "url": "https://github.com/o/r/pull/1",
        "number": 1,
        "title": "t",
        "baseRefName": "main",
        "headRefName": "f",
        "headRefOid": "a" * 40,
        "author": {"login": "u"},
    }
    kwargs = {
        "owner": "o",
        "repo": "r",
        "max_iterations": 15,
        "started_at": "2026-08-19T00:00:00Z",
        "meta": meta,
    }
    assert build_initial_state(**kwargs, dry_run=True)["dry_run"] is True
    assert build_initial_state(**kwargs)["dry_run"] is False
