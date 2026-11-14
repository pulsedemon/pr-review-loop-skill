#!/usr/bin/env python3
"""Shared state and metric helpers for the PR review loop."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from comment_context import _comment_projection, _disposition_roots, _reviewed_comments

# Source of truth: reviewers/personas.yaml `panel:`. This duplicate is kept here
# so state operations stay free of a runtime pyyaml dependency (preconditions
# require only gh/git/jq). Drift is guarded by test_approver_list_matches_manifest
# in scripts/tests/test_pr_loop_state.py — update both together.
APPROVER_LIST = [
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
DEFAULT_ADVERSARY_PANEL_VISIBILITY = "full"
ALLOWED_STATE_STATUSES = {
    "running",
    "success",
    "max_iterations",
    "no_progress",
    "tests_regressed",
    "ci_stuck",
    "external_push",
    "scope_split_recommended",
    "dry_run_complete",
    "setup_error",
    "review_incomplete",
}
ALLOWED_CI_STATUSES = {"success", "failure", "timeout", "skipped", "pending"}
ALLOWED_PANEL_SELECTION_MODES = {"full", "delta_gated"}
ALLOWED_PR_SCOPE_VERDICTS = {"under_threshold", "atomic", "request_split"}
ALLOWED_PR_SCOPE_USER_DECISIONS = {"not_prompted", "declined_agent", "continue", "abort"}
REQUIRED_PANEL_SELECTION_KEYS = (
    "mode",
    "ran",
    "skipped",
    "gate_relevant",
    "gate_fail_open",
    "open_blocker_carryover",
)
REQUIRED_META_KEYS = (
    "url",
    "number",
    "title",
    "baseRefName",
    "headRefName",
    "headRefOid",
)


class StateValidationError(ValueError):
    """Raised when state.json content is missing or malformed."""


def validate_timestamp(value: Any, label: str) -> None:
    """reject missing, malformed, or timezone-less completion timestamps."""
    if (
        not isinstance(value, str)
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?"
            r"(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)",
            value,
        )
        is None
    ):
        raise StateValidationError(f"{label} must be a timestamp with a timezone")
    try:
        datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
    except ValueError as exc:
        raise StateValidationError(f"{label} must be a timestamp with a timezone") from exc


def has_completion_marker(state: dict[str, Any]) -> bool:
    if "completed_at" not in state:
        return False
    validate_timestamp(state["completed_at"], "completed_at")
    return True


def validate_comment_ledger(ledger: Any) -> None:
    if not isinstance(ledger, list):
        raise StateValidationError("comment_ledger must be a list")
    seen: set[str] = set()
    allowed = {"id", "source", "disposition", "replied_at", "reason"}
    for entry in ledger:
        if not isinstance(entry, dict) or set(entry) - allowed:
            raise StateValidationError("invalid comment_ledger entry")
        comment_id = entry.get("id")
        if not isinstance(comment_id, str) or not comment_id or comment_id in seen:
            raise StateValidationError("invalid comment_ledger entry")
        seen.add(comment_id)
        disposition = entry.get("disposition")
        if (
            entry.get("source") != "review_comment"
            or disposition not in ("addressed", "deferred")
            or (
                (disposition == "deferred" or "reason" in entry)
                and (not isinstance(entry.get("reason"), str) or not entry["reason"])
            )
        ):
            raise StateValidationError("invalid comment_ledger entry")
        validate_timestamp(entry.get("replied_at"), "comment_ledger.replied_at")


def build_initial_state(
    *,
    owner: str,
    repo: str,
    max_iterations: int,
    started_at: str,
    meta: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Build the initial state.json payload."""
    missing = [key for key in REQUIRED_META_KEYS if key not in meta]
    if missing:
        raise StateValidationError(f"meta JSON missing required key(s): {', '.join(missing)}")
    if max_iterations < 1:
        raise StateValidationError(
            f"max_iterations must be >= 1 for initial state (got '{max_iterations}')"
        )
    author = meta.get("author")
    pr_author = author.get("login", "") if isinstance(author, dict) else ""
    return {
        "pr_url": meta["url"],
        "pr_number": meta["number"],
        "owner": owner,
        "repo": repo,
        "title": meta["title"],
        "base_branch": meta["baseRefName"],
        "head_branch": meta["headRefName"],
        "initial_head_sha": meta["headRefOid"],
        "pr_author": pr_author,
        "loop_started_at": started_at,
        "iteration": 0,
        "max_iterations": max_iterations,
        "dry_run": dry_run,
        "status": "running",
        "history": [],
        "pr_scope_mode": "auto",
        "max_new_loc": 1000,
        "approvers_required": "all",
        "approvers_required_list": APPROVER_LIST.copy(),
        "suggestion_promotion_threshold": 2,
        "adversary_promotion": True,
        "adversary_solo_promotion": True,
        "adversary_panel_visibility": DEFAULT_ADVERSARY_PANEL_VISIBILITY,
        "shallow_adversary_runs": 0,
    }


def load_state(path: str | Path) -> dict[str, Any]:
    """Read and parse state.json."""
    try:
        with Path(path).open(encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise StateValidationError(f"failed to read state.json ({exc})") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateValidationError(f"failed to parse state.json ({exc})") from exc
    if not isinstance(data, dict):
        raise StateValidationError("state.json top level must be an object")
    return data


def _json_deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _validate_optional_status(status: Any) -> None:
    if status is None:
        return
    if not isinstance(status, str):
        raise StateValidationError("status must be a string when present")
    if status not in ALLOWED_STATE_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_STATE_STATUSES))
        raise StateValidationError(f"status must be one of: {allowed}")


def _validate_ci_status(ci_status: Any) -> None:
    if not isinstance(ci_status, str) or not ci_status.strip():
        raise StateValidationError("ci_status must be a non-empty string")
    if ci_status not in ALLOWED_CI_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_CI_STATUSES))
        raise StateValidationError(f"ci_status must be one of: {allowed}")


def _validate_ci_failed_checks(entry: dict[str, Any]) -> None:
    # Only a failure entry is constrained. CI_STUCK compares this visit's names
    # against the most recent earlier failure entry, so a failure that records
    # none lets a permanently-red check burn iterations unnoticed.
    if entry.get("ci_status") != "failure":
        return
    checks = entry.get("ci_failed_checks")
    if not isinstance(checks, list) or not checks:
        raise StateValidationError(
            "ci_failed_checks must be a non-empty list when ci_status is 'failure'"
        )
    for check in checks:
        if not isinstance(check, str) or not check.strip():
            raise StateValidationError("every ci_failed_checks entry must be a non-empty string")


def _validate_panel_selection(panel_selection: Any) -> None:
    if not isinstance(panel_selection, dict):
        raise StateValidationError("panel_selection must be an object")

    for field in REQUIRED_PANEL_SELECTION_KEYS:
        if field not in panel_selection:
            raise StateValidationError(f"panel_selection missing required field '{field}'")

    unexpected = sorted(set(panel_selection) - set(REQUIRED_PANEL_SELECTION_KEYS))
    if unexpected:
        raise StateValidationError(
            "panel_selection has unexpected field(s): " + ", ".join(unexpected)
        )

    mode = panel_selection["mode"]
    if mode not in ALLOWED_PANEL_SELECTION_MODES:
        allowed = ", ".join(sorted(ALLOWED_PANEL_SELECTION_MODES))
        raise StateValidationError(f"panel_selection.mode must be one of: {allowed}")

    for field in REQUIRED_PANEL_SELECTION_KEYS[1:]:
        value = panel_selection[field]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise StateValidationError(f"panel_selection.{field} must be a list of strings")


def _validate_non_negative_int(value: Any, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StateValidationError(f"{label} must be a non-negative integer")


def _validate_pr_scope_file_entry(file_entry: Any, label: str) -> None:
    if isinstance(file_entry, str):
        if not file_entry.strip():
            raise StateValidationError(f"{label} must be a non-empty string")
        return
    if not isinstance(file_entry, dict):
        raise StateValidationError(f"{label} must be a string or partial-file object")
    path = file_entry.get("path")
    hunks = file_entry.get("hunks")
    if not isinstance(path, str) or not path.strip():
        raise StateValidationError(f"{label}.path must be a non-empty string")
    if (
        not isinstance(hunks, list)
        or not hunks
        or any(not isinstance(item, str) or not item.strip() for item in hunks)
    ):
        raise StateValidationError(f"{label}.hunks must be a non-empty list of non-empty strings")


def _validate_pr_scope_update(pr_scope: dict[str, Any]) -> None:
    if "threshold" in pr_scope:
        threshold = pr_scope["threshold"]
        if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:
            raise StateValidationError("pr_scope.threshold must be an integer >= 1")
    if "new_loc_total" in pr_scope:
        _validate_non_negative_int(pr_scope["new_loc_total"], "pr_scope.new_loc_total")
    if "per_file" in pr_scope:
        per_file = pr_scope["per_file"]
        if not isinstance(per_file, list):
            raise StateValidationError("pr_scope.per_file must be a list")
        for index, entry in enumerate(per_file):
            label = f"pr_scope.per_file[{index}]"
            if not isinstance(entry, dict):
                raise StateValidationError(f"{label} must be an object")
            for field in ("path", "added", "deleted"):
                if field not in entry:
                    raise StateValidationError(f"{label} missing required field '{field}'")
            if not isinstance(entry["path"], str) or not entry["path"].strip():
                raise StateValidationError(f"{label}.path must be a non-empty string")
            _validate_non_negative_int(entry["added"], f"{label}.added")
            _validate_non_negative_int(entry["deleted"], f"{label}.deleted")
    if "excluded_paths" in pr_scope:
        excluded_paths = pr_scope["excluded_paths"]
        if not isinstance(excluded_paths, list) or any(
            not isinstance(item, str) or not item.strip() for item in excluded_paths
        ):
            raise StateValidationError("pr_scope.excluded_paths must be a list of strings")
    if "verdict" in pr_scope and pr_scope["verdict"] not in ALLOWED_PR_SCOPE_VERDICTS:
        allowed = ", ".join(sorted(ALLOWED_PR_SCOPE_VERDICTS))
        raise StateValidationError(f"pr_scope.verdict must be one of: {allowed}")
    if "verdict" in pr_scope and pr_scope["verdict"] in {"atomic", "request_split"}:
        summary = pr_scope.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise StateValidationError(
                "pr_scope.summary must be a non-empty string for atomic/request_split verdicts"
            )
    elif "summary" in pr_scope and not isinstance(pr_scope["summary"], str):
        raise StateValidationError("pr_scope.summary must be a string")
    if "splits" in pr_scope:
        splits = pr_scope["splits"]
        if not isinstance(splits, list):
            raise StateValidationError("pr_scope.splits must be a list")
        for split_index, split in enumerate(splits):
            label = f"pr_scope.splits[{split_index}]"
            if not isinstance(split, dict):
                raise StateValidationError(f"{label} must be an object")
            for field in ("name", "rationale", "files", "estimated_new_loc"):
                if field not in split:
                    raise StateValidationError(f"{label} missing required field '{field}'")
            for field in ("name", "rationale"):
                if not isinstance(split[field], str) or not split[field].strip():
                    raise StateValidationError(f"{label}.{field} must be a non-empty string")
            files = split["files"]
            if not isinstance(files, list):
                raise StateValidationError(f"{label}.files must be a list")
            for file_index, file_entry in enumerate(files):
                _validate_pr_scope_file_entry(file_entry, f"{label}.files[{file_index}]")
            _validate_non_negative_int(split["estimated_new_loc"], f"{label}.estimated_new_loc")
            if "depends_on" in split:
                depends_on = split["depends_on"]
                if not isinstance(depends_on, list) or any(
                    not isinstance(item, str) or not item.strip() for item in depends_on
                ):
                    raise StateValidationError(f"{label}.depends_on must be a list of strings")
    if "remaining_in_original" in pr_scope:
        remaining = pr_scope["remaining_in_original"]
        if not isinstance(remaining, list) or any(
            not isinstance(item, str) or not item.strip() for item in remaining
        ):
            raise StateValidationError("pr_scope.remaining_in_original must be a list of strings")
    if (
        "user_decision" in pr_scope
        and pr_scope["user_decision"] not in ALLOWED_PR_SCOPE_USER_DECISIONS
    ):
        allowed = ", ".join(sorted(ALLOWED_PR_SCOPE_USER_DECISIONS))
        raise StateValidationError(f"pr_scope.user_decision must be one of: {allowed}")


def apply_pr_scope_update(
    *, state: dict[str, Any], pr_scope: dict[str, Any] | None, status: str | None = None
) -> dict[str, Any]:
    """Return a copy of state with the Step 3.5 pr_scope block updated."""

    if not isinstance(state, dict):
        raise StateValidationError("state must be an object")
    _validate_optional_status(status)
    updated = _json_deep_copy(state)
    if pr_scope is None:
        updated.pop("pr_scope", None)
    else:
        if not isinstance(pr_scope, dict):
            raise StateValidationError("pr_scope update must be an object or null")
        _validate_pr_scope_update(pr_scope)
        updated["pr_scope"] = _json_deep_copy(pr_scope)
    if status is not None:
        updated["status"] = status
    return updated


def append_history_entry(
    *,
    state: dict[str, Any],
    entry: dict[str, Any],
    status: str | None = None,
    comment_updates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Append one history[] entry and advance the top-level iteration counter."""

    if not isinstance(state, dict):
        raise StateValidationError("state must be an object")
    if not isinstance(entry, dict):
        raise StateValidationError("history entry must be an object")
    ledger = state.get("comment_ledger", [])
    has_reviewed_comments = "human_comments" in entry and not state.get("dry_run", False)
    if comment_updates is not None or has_reviewed_comments:
        validate_comment_ledger(ledger)
    if comment_updates is not None:
        validate_comment_ledger(comment_updates)
        if comment_updates and not has_reviewed_comments:
            raise StateValidationError(
                "comment updates require reviewed comments in a non-dry-run append"
            )
    for field in ("head_sha_before", "head_sha_after", "findings", "ci_status", "panel_selection"):
        if field not in entry:
            raise StateValidationError(f"history entry missing required field '{field}'")
    _validate_optional_status(status)
    for field in ("head_sha_before", "head_sha_after"):
        if not isinstance(entry[field], str) or not entry[field].strip():
            raise StateValidationError(f"{field} must be a non-empty string")
    if not isinstance(entry["findings"], list):
        raise StateValidationError("findings must be a list")
    _validate_ci_status(entry["ci_status"])
    _validate_ci_failed_checks(entry)
    _validate_panel_selection(entry["panel_selection"])
    if "reviewers_completed" in entry:
        reviewers_completed = entry["reviewers_completed"]
        if (
            not isinstance(reviewers_completed, list)
            or any(not isinstance(name, str) or not name.strip() for name in reviewers_completed)
            or len(reviewers_completed) != len(set(reviewers_completed))
            or not set(reviewers_completed).issubset(APPROVER_LIST)
        ):
            raise StateValidationError("reviewers_completed must contain unique panel names")

    if has_reviewed_comments:
        current_comments = _comment_projection(entry["human_comments"])
        if current_comments is None:
            raise StateValidationError("cannot record incomplete reviewed comments")
        handled = {receipt["id"] for receipt in ledger}
        needed = _disposition_roots(
            _reviewed_comments(state),
            current_comments,
            handled,
            code_changed=entry["head_sha_before"] != entry["head_sha_after"],
        )
        recorded = {receipt["id"] for receipt in comment_updates or []}
        missing = sorted(needed - recorded)
        if missing:
            raise StateValidationError("missing fresh comment dispositions: " + ", ".join(missing))

    updated = _json_deep_copy(state)
    if comment_updates is not None:
        updated_ledger = {receipt["id"]: receipt for receipt in ledger}
        updated_ledger.update({receipt["id"]: receipt for receipt in comment_updates})
        updated["comment_ledger"] = _json_deep_copy(list(updated_ledger.values()))
    history = updated.get("history")
    if history is None:
        history = []
        updated["history"] = history
    if not isinstance(history, list):
        raise StateValidationError("state.json field 'history' must be a list")

    current_iteration = _validated_iteration(updated, require_present=False)
    next_iteration = current_iteration + 1
    entry_copy = _json_deep_copy(entry)
    explicit_iteration = entry_copy.get("iteration")
    if explicit_iteration is not None and explicit_iteration != next_iteration:
        raise StateValidationError(
            "history entry iteration must match next iteration "
            f"({next_iteration}, got '{explicit_iteration}')"
        )
    entry_copy["iteration"] = next_iteration
    history.append(entry_copy)
    updated["iteration"] = next_iteration
    if status is not None:
        updated["status"] = status
    return updated


def _validated_iteration(state: dict[str, Any], *, require_present: bool) -> int:
    raw = state.get("iteration")
    if raw is None and require_present:
        raise StateValidationError("state.json missing required .iteration field")
    if raw is None:
        return 0
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise StateValidationError(f".iteration must be a non-negative integer (got '{raw}')")
    return raw


def resume_decision(
    *, state: dict[str, Any], current_head: str, remote_head: str, dirty: bool = False
) -> dict[str, Any]:
    """return the next iteration or a terminal decision without changing state."""
    if dirty:
        return {
            "terminal_status": "EXTERNAL_PUSH",
            "reason": "working tree has uncommitted changes",
            "next_iteration": None,
        }

    completed = _validated_iteration(state, require_present=True)
    history = state.get("history")
    if not isinstance(history, list) or len(history) != completed:
        raise StateValidationError("history length must match completed iteration count")
    maximum = state.get("max_iterations")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
        raise StateValidationError("max_iterations must be an integer >= 1")
    if history:
        latest = history[-1]
        if (
            not isinstance(latest, dict)
            or not isinstance(latest.get("iteration"), int)
            or isinstance(latest["iteration"], bool)
            or latest["iteration"] != completed
        ):
            raise StateValidationError(
                "latest history iteration must match completed iteration count"
            )
        expected_head = latest.get("head_sha_after")
    else:
        expected_head = state.get("initial_head_sha")
    if not isinstance(expected_head, str) or not expected_head.strip():
        raise StateValidationError("recorded resume head must be a non-empty string")
    if current_head != expected_head or remote_head != expected_head:
        return {
            "terminal_status": "EXTERNAL_PUSH",
            "reason": "local or remote head differs from the recorded resume head",
            "next_iteration": None,
        }

    scope = _optional_dict(state.get("pr_scope"), "pr_scope")
    if scope.get("user_decision") == "abort":
        return {
            "terminal_status": "SCOPE_SPLIT_RECOMMENDED",
            "reason": "recorded scope decision is abort",
            "next_iteration": None,
        }
    if completed >= maximum:
        return {
            "terminal_status": "MAX_ITERATIONS",
            "reason": "all permitted iterations are complete",
            "next_iteration": None,
        }
    return {
        "terminal_status": None,
        "reason": "local and remote heads match the recorded resume head",
        "next_iteration": completed + 1,
    }


def _jq_default(value: Any, default: Any) -> Any:
    return default if value is None or value is False else value


def _default_if_none(value: Any, default: Any) -> Any:
    return default if value is None else value


def _required_field(state: dict[str, Any], field: str) -> Any:
    value = state.get(field)
    if value is None:
        raise StateValidationError(f"state.json missing required field '{field}'")
    return value


def _optional_list(value: Any, label: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise StateValidationError(f"{label} must be a list")
    return value


def _optional_dict(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise StateValidationError(f"{label} must be an object")
    return value


def _count_severity(findings: list[Any], severity: str) -> int:
    return sum(
        1
        for finding in findings
        if isinstance(finding, dict) and finding.get("severity") == severity
    )


def _count_promotion_reason(items: list[Any], promotion_reason: str) -> int:
    return sum(
        1
        for item in items
        if isinstance(item, dict) and item.get("promotion_reason") == promotion_reason
    )


def _count_non_empty_review_bodies(reviews: list[Any]) -> int:
    return sum(1 for review in reviews if isinstance(review, dict) and review.get("body", "") != "")


_MODEL_ROUTING_PHASES = ("delta_gate", "reviewer", "adversary")


def _build_models_summary(model_routing: dict[str, Any]) -> dict[str, str]:
    """Summarize history[-1].model_routing as phase -> resolved model label.

    Value is the concrete `model` string when the host recorded one, else the
    portable `tier` (e.g. 'inherit'). Only phases with a dict entry are
    emitted; non-dict phase entries are skipped. The caller
    (build_iteration_metric) always passes a dict: it runs model_routing
    through _optional_dict first, which normalizes an absent field to {}
    and rejects a non-dict, so this function never sees None itself.
    """
    summary: dict[str, str] = {}
    for phase in _MODEL_ROUTING_PHASES:
        entry = model_routing.get(phase)
        if not isinstance(entry, dict):
            continue
        model = entry.get("model")
        tier = entry.get("tier")
        if isinstance(model, str) and model:
            summary[phase] = model
        elif isinstance(tier, str) and tier:
            summary[phase] = tier
    return summary


def _history_tail(state: dict[str, Any]) -> dict[str, Any]:
    history = state.get("history")
    if history is not None and not isinstance(history, list):
        raise StateValidationError("state.json field 'history' must be a list")
    if not history:
        raise StateValidationError(
            "history[] is empty; refusing to emit zero-filled record "
            "(SKILL.md §4i contract violated)"
        )
    tail = history[-1]
    if not isinstance(tail, dict):
        raise StateValidationError("history[-1] must be an object")
    return tail


def build_iteration_metric(
    *,
    state: dict[str, Any],
    owner: str,
    repo: str,
    pr_number: int,
    timestamp: str,
) -> dict[str, Any]:
    """Build the per-iteration metric payload from state.json."""
    hist = _history_tail(state)
    iteration = _validated_iteration(state, require_present=True)
    findings = _optional_list(hist.get("findings"), "history[-1] field 'findings'")
    addressed = _optional_list(hist.get("addressed"), "history[-1] field 'addressed'")
    deferred = _optional_list(hist.get("deferred"), "history[-1] field 'deferred'")
    demoted = _optional_list(hist.get("demoted"), "history[-1] field 'demoted'")
    shallow_review = _optional_list(
        hist.get("shallow_review"), "history[-1] field 'shallow_review'"
    )
    reviewer_errors = _optional_list(
        hist.get("reviewer_errors"), "history[-1] field 'reviewer_errors'"
    )
    human_comments = _optional_dict(
        hist.get("human_comments"), "history[-1] field 'human_comments'"
    )
    issue_comments = _optional_list(
        human_comments.get("issue_comments"), "history[-1].human_comments.issue_comments"
    )
    review_comments = _optional_list(
        human_comments.get("review_comments"), "history[-1].human_comments.review_comments"
    )
    reviews = _optional_list(human_comments.get("reviews"), "history[-1].human_comments.reviews")
    model_routing = _optional_dict(hist.get("model_routing"), "history[-1] field 'model_routing'")

    return {
        "kind": "iteration",
        "ts": timestamp,
        "pr": f"{owner}/{repo}#{pr_number}",
        "iteration": iteration,
        "ci_status": _jq_default(hist.get("ci_status"), "skipped"),
        "n_blockers": _count_severity(findings, "blocker"),
        "n_suggestions": _count_severity(findings, "suggestion"),
        "n_nits": _count_severity(findings, "nit"),
        "n_demoted": len(demoted),
        "n_shallow": len(shallow_review),
        "n_reviewer_errors": len(reviewer_errors),
        "n_issue_comments": len(issue_comments),
        "n_review_comments": len(review_comments),
        "n_reviews": _count_non_empty_review_bodies(reviews),
        "promoted": {
            "multi_source": _count_promotion_reason(addressed, "multi_source"),
            "adversary_endorsed": _count_promotion_reason(addressed, "adversary_endorsed"),
            "evidence_gated_solo_adversary": _count_promotion_reason(
                addressed, "evidence_gated_solo_adversary"
            ),
        },
        "failed": {
            "evidence_verification": _count_promotion_reason(
                deferred, "evidence_verification_failed"
            )
        },
        "adversary_ran": (
            _jq_default(hist.get("adversary"), None) is not None
            or _jq_default(hist.get("adversary_error"), None) is not None
        ),
        "shallow_adversary_runs": _jq_default(state.get("shallow_adversary_runs"), 0),
        "models": _build_models_summary(model_routing),
    }


def _wall_clock_seconds(state: dict[str, Any], now: datetime | None) -> int:
    started_at = state.get("loop_started_at")
    if started_at is None:
        return -1
    if not isinstance(started_at, str):
        raise StateValidationError("loop_started_at must be a string when present")
    if not started_at:
        return -1
    current = now or datetime.now(UTC)
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StateValidationError(
            f"loop_started_at must be an ISO 8601 timestamp (got '{started_at}')"
        ) from exc
    if started.tzinfo is None:
        raise StateValidationError(
            f"loop_started_at must include a timezone offset or Z suffix (got '{started_at}')"
        )
    return int(current.timestamp()) - int(started.timestamp())


def build_terminal_metric(
    *,
    state: dict[str, Any],
    terminal_status: str,
    timestamp: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the terminal rollup metric payload from state.json."""
    if terminal_status.lower() not in ALLOWED_STATE_STATUSES - {"running"}:
        allowed = ", ".join(sorted(s.upper() for s in ALLOWED_STATE_STATUSES - {"running"}))
        raise StateValidationError(
            f"terminal status must be one of {allowed}, got '{terminal_status}'"
        )
    iteration = _validated_iteration(state, require_present=False)
    history = state.get("history")
    if not isinstance(history, list):
        raise StateValidationError("state.json field 'history' must be a present list")
    approvers_required_list = _optional_list(
        state.get("approvers_required_list"), "state.json field 'approvers_required_list'"
    )

    totals = {
        "blockers": 0,
        "suggestions": 0,
        "nits": 0,
        "demoted": 0,
        "shallow_iterations": 0,
        "reviewer_errors": 0,
        "promoted_multi_source": 0,
        "promoted_adversary_endorsed": 0,
        "promoted_evidence_gated_solo_adversary": 0,
        "evidence_verification_failed": 0,
        "issue_comments_seen_total": 0,
        "review_comments_seen_total": 0,
        "reviews_seen_total": 0,
    }

    for entry in history:
        if not isinstance(entry, dict):
            continue
        findings = _optional_list(entry.get("findings"), "history entry field 'findings'")
        totals["blockers"] += _count_severity(findings, "blocker")
        totals["suggestions"] += _count_severity(findings, "suggestion")
        totals["nits"] += _count_severity(findings, "nit")

        demoted = _optional_list(entry.get("demoted"), "history entry field 'demoted'")
        totals["demoted"] += len(demoted)

        shallow_review = _optional_list(
            entry.get("shallow_review"), "history entry field 'shallow_review'"
        )
        if shallow_review:
            totals["shallow_iterations"] += 1

        reviewer_errors = _optional_list(
            entry.get("reviewer_errors"), "history entry field 'reviewer_errors'"
        )
        totals["reviewer_errors"] += len(reviewer_errors)

        addressed = _optional_list(entry.get("addressed"), "history entry field 'addressed'")
        deferred = _optional_list(entry.get("deferred"), "history entry field 'deferred'")
        totals["promoted_multi_source"] += _count_promotion_reason(addressed, "multi_source")
        totals["promoted_adversary_endorsed"] += _count_promotion_reason(
            addressed, "adversary_endorsed"
        )
        totals["promoted_evidence_gated_solo_adversary"] += _count_promotion_reason(
            addressed, "evidence_gated_solo_adversary"
        )
        totals["evidence_verification_failed"] += _count_promotion_reason(
            deferred, "evidence_verification_failed"
        )

        human_comments = _optional_dict(
            entry.get("human_comments"), "history entry field 'human_comments'"
        )
        totals["issue_comments_seen_total"] += len(
            _optional_list(
                human_comments.get("issue_comments"),
                "history entry human_comments.issue_comments",
            )
        )
        totals["review_comments_seen_total"] += len(
            _optional_list(
                human_comments.get("review_comments"),
                "history entry human_comments.review_comments",
            )
        )
        totals["reviews_seen_total"] += _count_non_empty_review_bodies(
            _optional_list(human_comments.get("reviews"), "history entry human_comments.reviews")
        )

    return {
        "kind": "terminal",
        "ts": timestamp,
        "pr": (
            f"{_required_field(state, 'owner')}/"
            f"{_required_field(state, 'repo')}#{_required_field(state, 'pr_number')}"
        ),
        "terminal_status": terminal_status,
        "iterations_completed": iteration,
        "wall_clock_seconds": _wall_clock_seconds(state, now),
        "knobs": {
            "max_iterations": state.get("max_iterations"),
            "approvers_required": _jq_default(state.get("approvers_required"), "all"),
            "pr_scope": _jq_default(state.get("pr_scope_mode"), "auto"),
            "max_new_loc": _jq_default(state.get("max_new_loc"), 1000),
            "suggestion_promotion_threshold": _jq_default(
                state.get("suggestion_promotion_threshold"), 2
            ),
            "adversary_promotion": _default_if_none(state.get("adversary_promotion"), True),
            "adversary_solo_promotion": _default_if_none(
                state.get("adversary_solo_promotion"), True
            ),
            "adversary_panel_visibility": _jq_default(
                state.get("adversary_panel_visibility"), DEFAULT_ADVERSARY_PANEL_VISIBILITY
            ),
        },
        "panel_size": len(approvers_required_list),
        "totals": totals,
    }


def _print_json(payload: dict[str, Any] | bool) -> int:
    json.dump(payload, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return 0


def write_state_file(path: str | Path, payload: dict[str, Any]) -> None:
    """Atomically write state.json using the canonical compact format."""

    target = Path(path)
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    except OSError as exc:
        raise StateValidationError(f"failed to write state.json ({exc})") from exc

    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"), sort_keys=True)
            fh.write("\n")
        tmp_path.replace(target)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise StateValidationError(f"failed to write state.json ({exc})") from exc


def _load_json_arg(raw: str, label: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StateValidationError(f"failed to parse {label} JSON ({exc})") from exc


def _load_append_json_arg(raw: str, label: str) -> Any:
    if raw != "-":
        return _load_json_arg(raw, label)
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StateValidationError(f"failed to parse {label} JSON ({exc})") from exc


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-state")
    init_parser.add_argument("--owner", required=True)
    init_parser.add_argument("--repo", required=True)
    init_parser.add_argument("--max-iterations", required=True, type=int)
    init_parser.add_argument("--started-at", required=True)
    init_parser.add_argument("--meta-json", required=True)
    init_parser.add_argument("--dry-run", action="store_true")

    iteration_parser = subparsers.add_parser("iteration-metric")
    iteration_parser.add_argument("--state", required=True)
    iteration_parser.add_argument("--owner", required=True)
    iteration_parser.add_argument("--repo", required=True)
    iteration_parser.add_argument("--pr-number", required=True, type=int)
    iteration_parser.add_argument("--timestamp", required=True)
    iteration_parser.add_argument("--script-name", default="write_iteration_metric")

    terminal_parser = subparsers.add_parser("terminal-metric")
    terminal_parser.add_argument("--state", required=True)
    terminal_parser.add_argument("--terminal-status", required=True)
    terminal_parser.add_argument("--timestamp", required=True)
    terminal_parser.add_argument("--script-name", default="write_terminal_metric")

    append_history_parser = subparsers.add_parser("append-history")
    append_history_parser.add_argument("--state", required=True)
    append_input = append_history_parser.add_mutually_exclusive_group(required=True)
    append_input.add_argument("--entry-json")
    append_input.add_argument("--input-json")
    append_history_parser.add_argument("--status")
    append_history_parser.add_argument("--script-name", default="pr_loop_state")

    resume_parser = subparsers.add_parser("resume-decision")
    resume_parser.add_argument("--state", required=True)
    resume_parser.add_argument("--current-head", required=True)
    resume_parser.add_argument("--remote-head", required=True)
    resume_parser.add_argument("--dirty", action="store_true")

    completion_parser = subparsers.add_parser("completion-marker")
    completion_parser.add_argument("--state", required=True)

    args = parser.parse_args(argv)

    try:
        if args.command == "init-state":
            meta = _load_json_arg(args.meta_json, "meta")
            if not isinstance(meta, dict):
                raise StateValidationError("meta JSON must be an object")
            return _print_json(
                build_initial_state(
                    owner=args.owner,
                    repo=args.repo,
                    max_iterations=args.max_iterations,
                    started_at=args.started_at,
                    meta=meta,
                    dry_run=args.dry_run,
                )
            )

        state = load_state(args.state)
        if args.command == "completion-marker":
            return _print_json(has_completion_marker(state))
        if args.command == "resume-decision":
            return _print_json(
                resume_decision(
                    state=state,
                    current_head=args.current_head,
                    remote_head=args.remote_head,
                    dirty=args.dirty,
                )
            )
        if args.command == "append-history":
            comment_updates = None
            if args.input_json is not None:
                payload = _load_append_json_arg(args.input_json, "append input")
                if not isinstance(payload, dict):
                    raise StateValidationError("append input JSON must be an object")
                entry = payload.get("entry")
                comment_updates = payload.get("comment_updates")
            else:
                entry = _load_append_json_arg(args.entry_json, "history entry")
            if not isinstance(entry, dict):
                raise StateValidationError("history entry JSON must be an object")
            updated = append_history_entry(
                state=state,
                entry=entry,
                status=args.status,
                comment_updates=comment_updates,
            )
            write_state_file(args.state, updated)
            return _print_json(updated)
        if args.command == "iteration-metric":
            return _print_json(
                build_iteration_metric(
                    state=state,
                    owner=args.owner,
                    repo=args.repo,
                    pr_number=args.pr_number,
                    timestamp=args.timestamp,
                )
            )
        return _print_json(
            build_terminal_metric(
                state=state,
                terminal_status=args.terminal_status,
                timestamp=args.timestamp,
            )
        )
    except StateValidationError as exc:
        script_name = getattr(args, "script_name", "pr_loop_state")
        print(f"{script_name}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(_main())
