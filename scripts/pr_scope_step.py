#!/usr/bin/env python3
"""Deterministic helpers for SKILL.md Step 3.5 PR-scope handling."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from _json_args import load_json_or_file
from pr_loop_state import (  # type: ignore[import-not-found]
    StateValidationError,
    apply_pr_scope_update,
    load_state,
    write_state_file,
)
from validate_pr_scope_output import (  # type: ignore[import-not-found]
    PrScopeOutputValidationError,
    validate_pr_scope_output,
)


class PrScopeStepError(ValueError):
    """Raised when Step 3.5 inputs are missing or malformed."""


ALLOWED_PERSIST_ACTIONS = frozenset({"skip", "continue", "prompt", "terminal"})


def _normalize_pr_scope_mode(mode: str) -> str:
    if mode not in {"auto", "true", "false"}:
        raise PrScopeStepError(f"pr_scope_mode must be one of auto/true/false (got '{mode}')")
    return mode


def _coerce_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PrScopeStepError(f"{label} must be an integer (got '{value}')")
    return value


def _require_positive_int(value: Any, label: str) -> int:
    parsed = _coerce_int(value, label)
    if parsed < 1:
        raise PrScopeStepError(f"{label} must be >= 1 (got '{parsed}')")
    return parsed


def _parse_count_stdout(stdout: str, threshold: int) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise PrScopeStepError("count_new_loc stdout must include the total on line 1")

    new_loc_total = _coerce_int(_parse_int(lines[0], "new_loc_total"), "new_loc_total")
    per_file: list[dict[str, Any]] = []
    for index, line in enumerate(lines[1:], start=2):
        try:
            added_raw, deleted_raw, path = line.split("\t", 2)
        except ValueError as exc:
            raise PrScopeStepError(
                f"count_new_loc stdout line {index} must be TSV <added>\\t<deleted>\\t<path>"
            ) from exc
        added = _parse_int(added_raw, f"stdout line {index} added")
        deleted = _parse_int(deleted_raw, f"stdout line {index} deleted")
        per_file.append({"added": added, "deleted": deleted, "path": path})

    return {
        "threshold": threshold,
        "new_loc_total": new_loc_total,
        "per_file": per_file,
    }


def _parse_int(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise PrScopeStepError(f"{label} must be an integer (got '{value}')") from exc
    if parsed < 0:
        raise PrScopeStepError(f"{label} must be >= 0 (got '{parsed}')")
    return parsed


def _parse_excluded_paths(stderr: str) -> list[str]:
    excluded: list[str] = []
    for index, line in enumerate(stderr.splitlines(), start=1):
        trimmed = line.strip()
        if not trimmed:
            continue
        for prefix in ("# excluded (binary):", "# excluded:"):
            if trimmed.startswith(prefix):
                path = trimmed.removeprefix(prefix).strip()
                if not path:
                    raise PrScopeStepError(
                        f"excluded path on stderr line {index} must be non-empty"
                    )
                excluded.append(path)
                break
        else:
            raise PrScopeStepError(
                "count_new_loc stderr lines must start with '# excluded: ' or "
                f"'# excluded (binary): ' (line {index}: '{trimmed}')"
            )
    return excluded


def _copy_pr_scope_record(pr_scope: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(pr_scope))


def _with_reused_existing_count(
    outcome: dict[str, Any], *, reused_existing_count: bool
) -> dict[str, Any]:
    return {**outcome, "reused_existing_count": reused_existing_count}


def plan_pr_scope_step(
    *,
    pr_scope_mode: str,
    threshold: int,
    count_stdout: str | None = None,
    count_stderr: str | None = None,
    existing_pr_scope: dict[str, Any] | None = None,
    pr_scope_file_exists: bool = False,
) -> dict[str, Any]:
    """Plan the deterministic Step 3.5 branch before any user interaction."""

    mode = _normalize_pr_scope_mode(pr_scope_mode)
    threshold = _require_positive_int(threshold, "threshold")

    if mode == "false":
        return {"action": "skip", "reused_existing_count": False, "pr_scope": None}

    if existing_pr_scope is not None:
        if not isinstance(existing_pr_scope, dict):
            raise PrScopeStepError("existing pr_scope must be an object")
        pr_scope = _copy_pr_scope_record(existing_pr_scope)
        user_decision = pr_scope.get("user_decision")
        if user_decision in {"not_prompted", "declined_agent", "agent_failed", "continue"}:
            return _with_reused_existing_count(
                {"action": "continue", "pr_scope": pr_scope},
                reused_existing_count=True,
            )
        if user_decision == "abort":
            return _with_reused_existing_count(
                {
                    "action": "terminal",
                    "pr_scope": pr_scope,
                    "status": "scope_split_recommended",
                },
                reused_existing_count=True,
            )
        if not pr_scope_file_exists:
            if pr_scope.get("new_loc_total") is None:
                raise PrScopeStepError(
                    "pr_scope_file_exists is required when reusing a partial Step 3.5 "
                    "record without a recorded user_decision or persisted new_loc_total"
                )
        outcome = _step_two_outcome(pr_scope, mode, threshold=threshold)
        return _with_reused_existing_count(outcome, reused_existing_count=True)

    if count_stdout is None or count_stderr is None:
        raise PrScopeStepError(
            "count_stdout and count_stderr are required for a fresh Step 3.5 run"
        )

    pr_scope = _parse_count_stdout(count_stdout, threshold)
    pr_scope["excluded_paths"] = _parse_excluded_paths(count_stderr)
    outcome = _step_two_outcome(pr_scope, mode, threshold=threshold)
    return _with_reused_existing_count(outcome, reused_existing_count=False)


def _step_two_outcome(pr_scope: dict[str, Any], mode: str, *, threshold: int) -> dict[str, Any]:
    new_loc_total = _coerce_int(pr_scope.get("new_loc_total"), "pr_scope.new_loc_total")
    threshold = _require_positive_int(threshold, "threshold")

    updated = _copy_pr_scope_record(pr_scope)
    updated["threshold"] = threshold
    if new_loc_total <= threshold and mode != "true":
        updated["verdict"] = "under_threshold"
        updated["user_decision"] = "not_prompted"
        return {"action": "continue", "pr_scope": updated}
    return {"action": "prompt", "pr_scope": updated}


def finalize_pr_scope_decision(
    *,
    pr_scope: dict[str, Any],
    user_decision: str,
    gate_result: dict[str, Any] | None = None,
    agent_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Merge the prompted decision, optional gate result and scope-agent errors into the
    PR-scope record."""

    if user_decision not in {"declined_agent", "agent_failed", "continue", "abort"}:
        raise PrScopeStepError(
            "user_decision must be one of declined_agent/agent_failed/continue/abort "
            f"(got '{user_decision}')"
        )

    updated = _copy_pr_scope_record(pr_scope)
    if agent_errors:
        updated["agent_errors"] = agent_errors

    if user_decision in {"declined_agent", "agent_failed"}:
        # a resumed record replanned with pr_scope_mode=true reaches here with its old verdict
        for field in ("verdict", "summary", "splits", "remaining_in_original"):
            updated.pop(field, None)
        updated["user_decision"] = user_decision
        return {"status": None, "pr_scope": updated}

    if gate_result is None:
        raise PrScopeStepError("gate_result is required when user_decision is continue or abort")
    if not isinstance(gate_result, dict):
        raise PrScopeStepError("gate_result must be an object")
    if gate_result.get("gate") != "pr-scope":
        raise PrScopeStepError("gate_result.gate must equal 'pr-scope'")

    verdict = gate_result.get("verdict")
    if verdict not in {"atomic", "request_split"}:
        raise PrScopeStepError(
            f"gate_result.verdict must be atomic or request_split (got '{verdict}')"
        )

    summary = gate_result.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise PrScopeStepError("gate_result.summary must be a non-empty string")

    try:
        validate_pr_scope_output(
            payload=gate_result,
            per_file=pr_scope.get("per_file", []),
            excluded_paths=pr_scope.get("excluded_paths", []),
            new_loc_total=_coerce_int(pr_scope.get("new_loc_total"), "pr_scope.new_loc_total"),
        )
    except PrScopeOutputValidationError as exc:
        raise PrScopeStepError(str(exc)) from exc

    updated["verdict"] = verdict
    updated["summary"] = summary
    if user_decision == "abort" and verdict != "request_split":
        raise PrScopeStepError("user_decision abort requires gate_result.verdict request_split")
    if verdict == "request_split":
        updated["splits"] = gate_result.get("splits", [])
        updated["remaining_in_original"] = gate_result.get("remaining_in_original", [])
    else:
        updated.pop("splits", None)
        updated.pop("remaining_in_original", None)
    updated["user_decision"] = user_decision

    status = "scope_split_recommended" if user_decision == "abort" else None
    return {"status": status, "pr_scope": updated}


def _resolve_persist_action(outcome: dict[str, Any]) -> str:
    """Map plan/finalize CLI JSON to a persist action."""

    action = outcome.get("action")
    if action in ALLOWED_PERSIST_ACTIONS:
        return action
    if action is not None:
        allowed = ", ".join(sorted(ALLOWED_PERSIST_ACTIONS))
        raise PrScopeStepError(f"outcome.action must be one of {allowed} (got '{action}')")
    status = outcome.get("status")
    if status == "scope_split_recommended":
        return "terminal"
    if isinstance(outcome.get("pr_scope"), dict):
        return "continue"
    allowed = ", ".join(sorted(ALLOWED_PERSIST_ACTIONS))
    raise PrScopeStepError(
        f"outcome.action must be one of {allowed} or inferrable from finalize output"
    )


def persist_pr_scope_outcome(
    *,
    state_path: str | Path,
    pr_scope_path: str | Path,
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """Persist non-skip Step 3.5 outcomes; skip outcomes leave state untouched."""

    state_file = Path(state_path)
    pr_scope_file = Path(pr_scope_path)
    try:
        state = load_state(state_file)
    except StateValidationError as exc:
        raise PrScopeStepError(str(exc)) from exc

    action = _resolve_persist_action(outcome)
    if action == "skip":
        return state

    pr_scope = outcome.get("pr_scope")
    if not isinstance(pr_scope, dict):
        raise PrScopeStepError("non-skip Step 3.5 outcomes must include a pr_scope object")

    try:
        state = apply_pr_scope_update(
            state=state,
            pr_scope=_copy_pr_scope_record(pr_scope),
            status=outcome.get("status"),
        )
    except StateValidationError as exc:
        raise PrScopeStepError(str(exc)) from exc
    pr_scope_payload = json.dumps(pr_scope, indent=2, sort_keys=True) + "\n"
    original_state = state_file.read_text(encoding="utf-8") if state_file.exists() else None

    try:
        write_state_file(state_file, state)
    except StateValidationError as exc:
        raise PrScopeStepError(f"failed to write state file ({exc})") from exc

    try:
        pr_scope_tmp = _write_temp_json(pr_scope_file, pr_scope_payload, "pr_scope file")
        pr_scope_tmp.replace(pr_scope_file)
    except PrScopeStepError:
        _restore_original_state(state_file, original_state)
        raise
    except OSError as exc:
        _restore_original_state(state_file, original_state)
        raise PrScopeStepError(f"failed to write pr_scope file ({exc})") from exc
    return state


def _write_temp_json(target: Path, payload: str, label: str) -> Path:
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=".pr-loop-", dir=target.parent)
    except OSError as exc:
        raise PrScopeStepError(f"failed to write {label} ({exc})") from exc

    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise PrScopeStepError(f"failed to write {label} ({exc})") from exc
    return tmp_path


def _restore_original_state(target: Path, payload: str | None) -> None:
    try:
        if payload is None:
            target.unlink(missing_ok=True)
            return
        tmp_path = _write_temp_json(target, payload, "state restore file")
        tmp_path.replace(target)
    except (OSError, PrScopeStepError) as exc:
        raise PrScopeStepError(
            f"failed to restore original state after pr_scope write failure ({exc})"
        ) from exc


def _print_json(payload: dict[str, Any]) -> int:
    json.dump(payload, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--pr-scope-mode", required=True)
    plan_parser.add_argument("--threshold", required=True, type=int)
    plan_parser.add_argument("--count-stdout-file")
    plan_parser.add_argument("--count-stderr-file")
    plan_parser.add_argument("--existing-pr-scope-json")
    plan_parser.add_argument("--existing-pr-scope-json-file")
    plan_parser.add_argument("--pr-scope-file-exists", action="store_true")

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--pr-scope-json")
    finalize_parser.add_argument("--pr-scope-json-file")
    finalize_parser.add_argument("--user-decision", required=True)
    finalize_parser.add_argument("--gate-result-json")
    finalize_parser.add_argument("--gate-result-json-file")
    finalize_parser.add_argument("--agent-error", action="append")

    persist_parser = subparsers.add_parser("persist")
    persist_parser.add_argument("--state", required=True)
    persist_parser.add_argument("--pr-scope-path", required=True)
    persist_parser.add_argument("--outcome-json")
    persist_parser.add_argument("--outcome-json-file")

    args = parser.parse_args(argv)

    try:
        if args.command == "plan":
            existing_pr_scope = load_json_or_file(
                inline=args.existing_pr_scope_json,
                file_path=args.existing_pr_scope_json_file,
                label="existing pr_scope",
                flag_stem="existing-pr-scope",
                error_cls=PrScopeStepError,
                required=False,
            )
            if existing_pr_scope is not None and not isinstance(existing_pr_scope, dict):
                raise PrScopeStepError("existing pr_scope JSON must be an object")
            try:
                count_stdout = (
                    Path(args.count_stdout_file).read_text(encoding="utf-8")
                    if args.count_stdout_file
                    else None
                )
                count_stderr = (
                    Path(args.count_stderr_file).read_text(encoding="utf-8")
                    if args.count_stderr_file
                    else None
                )
            except UnicodeDecodeError as exc:
                raise PrScopeStepError(f"failed to read count file ({exc})") from exc
            return _print_json(
                plan_pr_scope_step(
                    pr_scope_mode=args.pr_scope_mode,
                    threshold=args.threshold,
                    count_stdout=count_stdout,
                    count_stderr=count_stderr,
                    existing_pr_scope=existing_pr_scope,
                    pr_scope_file_exists=args.pr_scope_file_exists,
                )
            )

        if args.command == "finalize":
            pr_scope = load_json_or_file(
                inline=args.pr_scope_json,
                file_path=args.pr_scope_json_file,
                label="pr_scope",
                flag_stem="pr-scope",
                error_cls=PrScopeStepError,
            )
            gate_result = load_json_or_file(
                inline=args.gate_result_json,
                file_path=args.gate_result_json_file,
                label="gate_result",
                flag_stem="gate-result",
                error_cls=PrScopeStepError,
                required=False,
            )
            if not isinstance(pr_scope, dict):
                raise PrScopeStepError("pr_scope JSON must be an object")
            if gate_result is not None and not isinstance(gate_result, dict):
                raise PrScopeStepError("gate_result JSON must be an object")
            return _print_json(
                finalize_pr_scope_decision(
                    pr_scope=pr_scope,
                    user_decision=args.user_decision,
                    gate_result=gate_result,
                    agent_errors=args.agent_error,
                )
            )

        outcome = load_json_or_file(
            inline=args.outcome_json,
            file_path=args.outcome_json_file,
            label="outcome",
            flag_stem="outcome",
            error_cls=PrScopeStepError,
        )
        if not isinstance(outcome, dict):
            raise PrScopeStepError("outcome JSON must be an object")
        return _print_json(
            persist_pr_scope_outcome(
                state_path=args.state,
                pr_scope_path=args.pr_scope_path,
                outcome=outcome,
            )
        )
    except (OSError, PrScopeStepError, StateValidationError) as exc:
        print(f"pr_scope_step: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
