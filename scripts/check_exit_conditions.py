#!/usr/bin/env python3
"""decide iteration boundaries, comment completion, NO_PROGRESS, and CI_STUCK.

stdin accepts blockers and ci_failed_checks for the existing comparisons.
phases entry and comments use state.iteration + 1; comments requires a complete
comment envelope and returns disposition_root_ids plus continue_full_panel.
edit requires the active iteration;
completion requires iteration, comments, current_head, remote_head, and a completed
current review record in state.
stdout contains terminal_status and reason, plus continue_full_panel on a
nonterminal completion decision. --state selects the persisted state file.
exit 0 emits a decision; exit 2 reports malformed input.
"""

import argparse
import json
import sys
from pathlib import Path

from jsonschema.exceptions import SchemaError

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from comment_context import (  # noqa: E402
    _comment_projection,
    _discussion_changes,
    _disposition_roots,
    _reviewed_comments,
)
from finding_contract import is_open_blocker, promoted_keys, well_formed  # noqa: E402
from finding_matcher import is_match_or_summary  # noqa: E402
from flag_shallow_reviews import is_shallow  # noqa: E402
from pr_loop_state import (  # noqa: E402
    APPROVER_LIST,
    StateValidationError,
    load_state,
    validate_comment_ledger,
)
from validate_reviewer_output import load_validator  # noqa: E402

LOOKBACK = 2


def _blockers(entry: dict) -> list[dict] | None:
    """The entry's effective blocker set, or None if it cannot be trusted.

    state.json was written by a previous iteration, so malformed data is not a
    caller error to reject with exit 2. But skipping the bad items would leave
    a smaller set that a current set could match exactly, firing NO_PROGRESS on
    a blocker set that genuinely shrank. Treat the whole entry as unusable.
    """
    findings = entry.get("findings")
    if not isinstance(findings, list):
        return None
    promoted = promoted_keys(entry)
    if promoted is None:
        return None
    blockers = []
    for f in findings:
        if not isinstance(f, dict) or not well_formed(f):
            return None
        if is_open_blocker(f, promoted):
            blockers.append(f)
    return blockers


def _pairs_off(current: list[dict], previous: list[dict]) -> bool:
    """Whether every current blocker pairs with a distinct previous one.

    Augmenting-path matching rather than two containment scans: matching is
    neither transitive nor injective, so one current blocker can satisfy two
    previous ones (lines 10 and 20 both within the window of 15) and a set
    shrinking from two to one would read as unchanged.
    """
    partner: dict[int, int] = {}

    def assign(ci: int, seen: set[int]) -> bool:
        for pi, prev in enumerate(previous):
            if pi in seen or not is_match_or_summary(current[ci], prev):
                continue
            seen.add(pi)
            if pi not in partner or assign(partner[pi], seen):
                partner[pi] = ci
                return True
        return False

    return all(assign(ci, set()) for ci in range(len(current)))


def _same_set(current: list[dict], previous: list[dict]) -> bool:
    """Whether two blocker sets describe the same issues.

    Equal cardinality plus a one-to-one pairing. Containment alone, in either
    or both directions, lets candidates be reused: three blockers dropping to
    one is progress and must keep iterating.
    """
    if not current or not previous or len(current) != len(previous):
        return False
    return _pairs_off(current, previous)


def _check_no_progress(blockers: list[dict], history: list[dict]) -> str | None:
    # Compare against each of the last two entries separately. Pooling them
    # would let a current {A,B} match a union of {B} and {A} and fire on a set
    # that repeats neither iteration. An oscillation (A/B/A) repeats no
    # consecutive iteration, which is why history[-2] is consulted at all.
    for offset in range(1, LOOKBACK + 1):
        if len(history) < offset:
            break
        entry = history[-offset]
        if not isinstance(entry, dict):
            continue
        previous = _blockers(entry)
        if previous is not None and _same_set(blockers, previous):
            return f"blockers repeat history[-{offset}]"
    return None


def _check_ci_stuck(failed: list[str], history: list[dict]) -> str | None:
    # Walk back to the most recent entry that recorded failures. Iterations
    # that skip §4d.1 persist ci_status "skipped" and no ci_failed_checks, so
    # comparing against history[-1] would intersect with nothing and never
    # fire. Absent and [] mean the same thing: nothing recorded.
    if not failed:
        return None
    for entry in reversed(history):
        if not isinstance(entry, dict):
            continue
        # §4i records names only on a failure, so names riding on a success or
        # skipped entry are stale or malformed. Counting them would both fire
        # CI_STUCK spuriously and mask an older real failure behind them.
        if entry.get("ci_status") != "failure":
            continue
        previous = entry.get("ci_failed_checks")
        if not isinstance(previous, list) or not previous:
            continue
        # Intersection, not equality: {build, lint} followed by {build} is a
        # stuck build, and equality would read the departed lint as progress.
        shared = sorted(set(failed) & {c for c in previous if isinstance(c, str)})
        if shared:
            names = ", ".join(shared)
            return f"still failing since iteration {entry.get('iteration')}: {names}"
        return None
    return None


def _review_completion_reason(state: dict) -> str | None:
    required = state.get("approvers_required_list", APPROVER_LIST)
    if (
        not isinstance(required, list)
        or not required
        or any(not isinstance(name, str) or not name for name in required)
        or len(required) != len(set(required))
        or not set(required).issubset(APPROVER_LIST)
    ):
        raise StateValidationError("invalid approvers_required_list")

    history = state.get("history")
    if not isinstance(history, list) or not history:
        return "missing current review record"
    entry = history[-1]
    if (
        not isinstance(entry, dict)
        or type(entry.get("iteration")) is not int
        or entry["iteration"] != state.get("iteration")
    ):
        return "missing current review record"
    head_sha_before = entry.get("head_sha_before")
    if not isinstance(head_sha_before, str) or not head_sha_before.strip():
        return "current head requires review"
    if entry.get("head_sha_after") != head_sha_before:
        return "current head requires review"

    completed = entry.get("reviewers_completed")
    if (
        not isinstance(completed, list)
        or any(not isinstance(name, str) or not name for name in completed)
        or len(completed) != len(set(completed))
        or set(completed) != set(required)
    ):
        return "required panel reviews did not complete"
    reviewer_errors = entry.get("reviewer_errors", [])
    if not isinstance(reviewer_errors, list) or reviewer_errors:
        return "required panel review failed"
    if "adversary_error" in entry:
        return "final adversary review failed"

    try:
        validator = load_validator()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SchemaError, ValueError) as exc:
        raise StateValidationError(f"invalid or unreadable reviewer schema: {exc}") from exc
    adversary = entry.get("adversary")
    if not validator.is_valid(adversary):
        return "missing or invalid final adversary response"
    if adversary.get("reviewer") != "adversary":
        return "final adversary identity mismatch"
    if not adversary["findings"] and adversary["verdict"] != "approve":
        return "final adversary returned no findings without approval"
    if is_shallow(adversary) or (
        adversary["verdict"] == "approve"
        and not any(path.strip() for path in adversary["evidence"]["files_read"])
    ):
        return "final adversary approval lacks read evidence"
    if entry.get("adversary_shallow_giveup"):
        return "final adversary review did not complete"
    return None


def _completion(data: dict, state: dict) -> dict:
    for name in ("current_head", "remote_head"):
        value = data.get(name)
        if not isinstance(value, str) or not value.strip():
            raise StateValidationError(f"completion requires {name}")
    reason = _review_completion_reason(state)
    if reason is not None:
        return {"terminal_status": "REVIEW_INCOMPLETE", "reason": reason}
    reviewed_head = state["history"][-1]["head_sha_before"]
    if data["current_head"] != reviewed_head or data["remote_head"] != reviewed_head:
        return {"terminal_status": "EXTERNAL_PUSH", "reason": "head changed after review"}
    current = _comment_projection(data.get("comments"))
    if current is None:
        return {"terminal_status": "REVIEW_INCOMPLETE", "reason": "incomplete comment content"}
    previous = _reviewed_comments(state)
    if previous is None:
        return {"terminal_status": "REVIEW_INCOMPLETE", "reason": "missing reviewed comments"}
    ledger = state.get("comment_ledger", [])
    validate_comment_ledger(ledger)
    handled = {entry["id"] for entry in ledger}
    previous_required = {
        root_id for root_id, thread in previous["threads"].items() if thread["required"]
    }
    if previous_required - handled:
        return {
            "terminal_status": "REVIEW_INCOMPLETE",
            "reason": "required replies remain unhandled",
        }
    changed_roots, feedback_changed = _discussion_changes(previous, current)
    current_required = {
        root_id for root_id, thread in current["threads"].items() if thread["required"]
    }
    unchanged_unhandled = current_required & set(previous["threads"]) - handled - changed_roots
    if unchanged_unhandled:
        return {
            "terminal_status": "REVIEW_INCOMPLETE",
            "reason": "required replies remain unhandled",
        }
    if feedback_changed:
        if data["iteration"] >= state["max_iterations"]:
            return {
                "terminal_status": "MAX_ITERATIONS",
                "reason": "new comments require another iteration",
            }
        return {
            "terminal_status": None,
            "reason": "new review comments",
            "continue_full_panel": True,
        }
    return {
        "terminal_status": None,
        "reason": "comment handling complete",
        "continue_full_panel": False,
    }


def _comment_iteration(data: dict, state: dict) -> dict:
    current = _comment_projection(data.get("comments"))
    if current is None:
        return {"terminal_status": "REVIEW_INCOMPLETE", "reason": "incomplete comment content"}
    ledger = state.get("comment_ledger", [])
    validate_comment_ledger(ledger)
    code_changed = data.get("code_changed", False)
    if type(code_changed) is not bool:
        raise StateValidationError("code_changed must be a boolean")
    previous = _reviewed_comments(state)
    handled = {entry["id"] for entry in ledger}
    roots = _disposition_roots(
        previous,
        current,
        handled,
        code_changed=code_changed,
    )
    _, feedback_changed = _discussion_changes(previous, current)
    return {
        "terminal_status": None,
        "reason": "discussion context inspected",
        "disposition_root_ids": sorted(roots),
        "continue_full_panel": feedback_changed,
    }


def decide(data: dict, state: dict) -> dict:
    phase = data.get("phase")
    if phase is not None:
        if not isinstance(phase, str) or phase not in {"entry", "comments", "edit", "completion"}:
            raise StateValidationError("phase must be entry, comments, edit, or completion")
        limit = state.get("max_iterations")
        completed = state.get("iteration")
        if type(limit) is not int or limit < 1 or type(completed) is not int or completed < 0:
            raise StateValidationError("state requires valid iteration and max_iterations")
        iteration = completed + 1 if phase in {"entry", "comments"} else data.get("iteration")
        if type(iteration) is not int or iteration < 1:
            raise StateValidationError("iteration must be a positive integer")
        expected = completed if phase == "completion" else completed + 1
        if iteration != expected:
            raise StateValidationError("iteration does not match the persisted completed count")
        if iteration > limit or (phase == "edit" and iteration == limit):
            return {"terminal_status": "MAX_ITERATIONS", "reason": "iteration budget exhausted"}
        if phase == "completion":
            return _completion(data, state)
        if phase == "comments":
            return _comment_iteration(data, state)
        if phase == "entry":
            return {"terminal_status": None, "reason": "iteration budget available"}

    history = state.get("history")
    if not isinstance(history, list):
        history = []

    blockers = data.get("blockers") or []
    reason = _check_no_progress(blockers, history)
    if reason:
        return {"terminal_status": "NO_PROGRESS", "reason": reason}

    failed = data.get("ci_failed_checks") or []
    reason = _check_ci_stuck(failed, history)
    if reason:
        return {"terminal_status": "CI_STUCK", "reason": reason}

    return {"terminal_status": None, "reason": "no exit condition met"}


def _fail(message: str) -> int:
    print(f"check_exit_conditions: {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="check iteration, review completion, and repeated failures"
    )
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return _fail(f"stdin is not valid JSON: {e}")
    if not isinstance(data, dict):
        return _fail("stdin must be a JSON object")

    for key in ("blockers", "ci_failed_checks"):
        value = data.get(key)
        if value is not None and not isinstance(value, list):
            return _fail(f"{key} must be a list or null")
    for finding in data.get("blockers") or []:
        if not isinstance(finding, dict):
            return _fail("every blocker must be an object")
        if not isinstance(finding.get("summary"), str):
            return _fail("every blocker needs a string 'summary'")
        if finding.get("file") is not None and not isinstance(finding["file"], str):
            return _fail("every blocker's 'file' must be a string")
        # bool is an int subclass, and is_match coerces with int(), so `true`
        # would silently become line 1.
        line = finding.get("line")
        if line is not None and (not isinstance(line, int) or isinstance(line, bool)):
            return _fail("every blocker's 'line' must be an integer")
    for check in data.get("ci_failed_checks") or []:
        if not isinstance(check, str):
            return _fail("every ci_failed_checks entry must be a string")

    try:
        state = load_state(args.state)
    except StateValidationError as e:
        return _fail(str(e))

    try:
        decision = decide(data, state)
    except StateValidationError as e:
        return _fail(str(e))
    json.dump(decision, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
