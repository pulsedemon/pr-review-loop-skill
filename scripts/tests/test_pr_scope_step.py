"""Tests for scripts/pr_scope_step.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pr_scope_step import (  # type: ignore[import-not-found]
    PrScopeStepError,
    _main,
    finalize_pr_scope_decision,
    persist_pr_scope_outcome,
    plan_pr_scope_step,
)

COUNT_STDOUT = """282
180\t0\tsrc/feature/foo.ts
90\t0\tsrc/feature/foo.test.ts
12\t0\tREADME.md
"""


COUNT_STDERR = "# excluded: package-lock.json\n"


_SPLIT_PER_FILE = [
    {
        "path": "apps/web/server/middleware/catalog-preview.ts",
        "added": 410,
        "deleted": 0,
    },
    {"path": "docs/changelog.md", "added": 838, "deleted": 0},
]


def make_pr_scope_record(*, include_defaults: bool = True, **updates: object) -> dict[str, object]:
    record: dict[str, object] = {"threshold": 1000, "new_loc_total": 1248}
    if include_defaults:
        record["per_file"] = list(_SPLIT_PER_FILE)
        record["excluded_paths"] = ["pnpm-lock.yaml"]
    record.update(updates)
    return record


def make_request_split_gate_result(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "gate": "pr-scope",
        "verdict": "request_split",
        "summary": "Split middleware from billing.",
        "splits": [
            {
                "name": "catalog-preview middleware",
                "rationale": "Isolated feature.",
                "files": ["apps/web/server/middleware/catalog-preview.ts"],
                "estimated_new_loc": 410,
            }
        ],
        "remaining_in_original": ["docs/changelog.md"],
    }
    result.update(updates)
    return result


def test_plan_pr_scope_step_requires_count_streams_on_fresh_run() -> None:
    with pytest.raises(PrScopeStepError, match="count_stdout and count_stderr are required"):
        plan_pr_scope_step(pr_scope_mode="auto", threshold=1000)


def test_plan_pr_scope_step_under_threshold_records_not_prompted() -> None:
    outcome = plan_pr_scope_step(
        pr_scope_mode="auto",
        threshold=1000,
        count_stdout=COUNT_STDOUT,
        count_stderr=COUNT_STDERR,
    )

    assert outcome == {
        "action": "continue",
        "reused_existing_count": False,
        "pr_scope": {
            "threshold": 1000,
            "new_loc_total": 282,
            "per_file": [
                {"added": 180, "deleted": 0, "path": "src/feature/foo.ts"},
                {"added": 90, "deleted": 0, "path": "src/feature/foo.test.ts"},
                {"added": 12, "deleted": 0, "path": "README.md"},
            ],
            "excluded_paths": ["package-lock.json"],
            "verdict": "under_threshold",
            "user_decision": "not_prompted",
        },
    }


def test_plan_pr_scope_step_true_prompts_even_under_threshold() -> None:
    outcome = plan_pr_scope_step(
        pr_scope_mode="true",
        threshold=1000,
        count_stdout=COUNT_STDOUT,
        count_stderr=COUNT_STDERR,
    )

    assert outcome == {
        "action": "prompt",
        "reused_existing_count": False,
        "pr_scope": {
            "threshold": 1000,
            "new_loc_total": 282,
            "per_file": [
                {"added": 180, "deleted": 0, "path": "src/feature/foo.ts"},
                {"added": 90, "deleted": 0, "path": "src/feature/foo.test.ts"},
                {"added": 12, "deleted": 0, "path": "README.md"},
            ],
            "excluded_paths": ["package-lock.json"],
        },
    }


@pytest.mark.parametrize(
    "count_stderr",
    ["# excluded: \n", "# excluded (binary): \n"],
)
def test_plan_pr_scope_step_rejects_empty_excluded_path(count_stderr: str) -> None:
    with pytest.raises(PrScopeStepError, match="excluded path on stderr line 1"):
        plan_pr_scope_step(
            pr_scope_mode="auto",
            threshold=1000,
            count_stdout=COUNT_STDOUT,
            count_stderr=count_stderr,
        )


def test_plan_pr_scope_step_false_skips_counting_entirely() -> None:
    outcome = plan_pr_scope_step(
        pr_scope_mode="false",
        threshold=1000,
    )

    assert outcome == {
        "action": "skip",
        "reused_existing_count": False,
        "pr_scope": None,
    }


@pytest.mark.parametrize("threshold", [0, -1])
def test_plan_pr_scope_step_rejects_threshold_below_one(threshold: int) -> None:
    with pytest.raises(PrScopeStepError, match="threshold must be >= 1"):
        plan_pr_scope_step(
            pr_scope_mode="auto",
            threshold=threshold,
            count_stdout=COUNT_STDOUT,
            count_stderr=COUNT_STDERR,
        )


def test_plan_pr_scope_step_rejects_non_object_existing_pr_scope() -> None:
    with pytest.raises(PrScopeStepError, match="existing pr_scope must be an object"):
        plan_pr_scope_step(
            pr_scope_mode="auto",
            threshold=1000,
            existing_pr_scope=[],
            pr_scope_file_exists=True,
        )


def test_plan_pr_scope_step_resume_reuses_state_counts_without_pr_scope_file() -> None:
    outcome = plan_pr_scope_step(
        pr_scope_mode="auto",
        threshold=500,
        existing_pr_scope=make_pr_scope_record(
            new_loc_total=600,
            threshold=1000,
            include_defaults=False,
        ),
        pr_scope_file_exists=False,
    )

    assert outcome == {
        "action": "prompt",
        "reused_existing_count": True,
        "pr_scope": make_pr_scope_record(
            new_loc_total=600,
            threshold=500,
            include_defaults=False,
        ),
    }


def test_plan_pr_scope_step_resume_honors_state_decision_without_pr_scope_file() -> None:
    outcome = plan_pr_scope_step(
        pr_scope_mode="auto",
        threshold=1000,
        existing_pr_scope=make_pr_scope_record(user_decision="declined_agent"),
        pr_scope_file_exists=False,
    )

    assert outcome == {
        "action": "continue",
        "reused_existing_count": True,
        "pr_scope": make_pr_scope_record(user_decision="declined_agent"),
    }


@pytest.mark.parametrize("decision", ["not_prompted", "declined_agent", "agent_failed", "continue"])
def test_plan_pr_scope_step_resume_honors_recorded_decision(decision: str) -> None:
    outcome = plan_pr_scope_step(
        pr_scope_mode="auto",
        threshold=1000,
        existing_pr_scope=make_pr_scope_record(user_decision=decision),
        pr_scope_file_exists=True,
    )

    assert outcome == {
        "action": "continue",
        "reused_existing_count": True,
        "pr_scope": make_pr_scope_record(user_decision=decision),
    }


def test_plan_pr_scope_step_resume_missing_decision_under_threshold_continues() -> None:
    outcome = plan_pr_scope_step(
        pr_scope_mode="auto",
        threshold=1000,
        existing_pr_scope=make_pr_scope_record(new_loc_total=282),
        pr_scope_file_exists=True,
    )

    assert outcome == {
        "action": "continue",
        "reused_existing_count": True,
        "pr_scope": {
            **make_pr_scope_record(new_loc_total=282),
            "verdict": "under_threshold",
            "user_decision": "not_prompted",
        },
    }


def test_plan_pr_scope_step_resume_recompare_uses_cli_threshold_not_persisted() -> None:
    outcome = plan_pr_scope_step(
        pr_scope_mode="auto",
        threshold=500,
        existing_pr_scope=make_pr_scope_record(
            new_loc_total=600,
            threshold=1000,
            include_defaults=False,
        ),
        pr_scope_file_exists=True,
    )

    assert outcome == {
        "action": "prompt",
        "reused_existing_count": True,
        "pr_scope": make_pr_scope_record(
            new_loc_total=600,
            threshold=500,
            include_defaults=False,
        ),
    }


def test_plan_pr_scope_step_resume_missing_decision_reuses_count_then_prompts() -> None:
    outcome = plan_pr_scope_step(
        pr_scope_mode="auto",
        threshold=1000,
        existing_pr_scope=make_pr_scope_record(
            per_file=[
                {
                    "added": 410,
                    "deleted": 0,
                    "path": "apps/web/server/middleware/catalog-preview.ts",
                }
            ]
        ),
        pr_scope_file_exists=True,
    )

    assert outcome == {
        "action": "prompt",
        "reused_existing_count": True,
        "pr_scope": make_pr_scope_record(
            per_file=[
                {
                    "added": 410,
                    "deleted": 0,
                    "path": "apps/web/server/middleware/catalog-preview.ts",
                }
            ]
        ),
    }


@pytest.mark.parametrize("threshold", [0, -1])
def test_plan_pr_scope_step_resume_rejects_cli_threshold_below_one(
    threshold: int,
) -> None:
    with pytest.raises(PrScopeStepError, match="threshold must be >= 1"):
        plan_pr_scope_step(
            pr_scope_mode="auto",
            threshold=threshold,
            existing_pr_scope=make_pr_scope_record(new_loc_total=600),
            pr_scope_file_exists=True,
        )


def test_plan_pr_scope_step_resume_abort_re_emits_terminal_status() -> None:
    outcome = plan_pr_scope_step(
        pr_scope_mode="auto",
        threshold=1000,
        existing_pr_scope=make_pr_scope_record(
            include_defaults=False,
            verdict="request_split",
            user_decision="abort",
        ),
        pr_scope_file_exists=True,
    )

    assert outcome == {
        "action": "terminal",
        "reused_existing_count": True,
        "pr_scope": make_pr_scope_record(
            include_defaults=False,
            verdict="request_split",
            user_decision="abort",
        ),
        "status": "scope_split_recommended",
    }


def test_persist_pr_scope_outcome_infers_action_from_finalize_output(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    pr_scope_path = tmp_path / "pr-scope.json"
    state_path.write_text('{"status":"running","history":[]}\n', encoding="utf-8")

    updated_state = persist_pr_scope_outcome(
        state_path=state_path,
        pr_scope_path=pr_scope_path,
        outcome={
            "status": None,
            "pr_scope": make_pr_scope_record(user_decision="declined_agent"),
        },
    )

    assert updated_state["pr_scope"]["user_decision"] == "declined_agent"
    assert pr_scope_path.exists()


def test_finalize_pr_scope_decision_records_agent_failed() -> None:
    decision = finalize_pr_scope_decision(
        pr_scope=make_pr_scope_record(),
        user_decision="agent_failed",
        agent_errors=["launch refused"],
    )

    assert decision == {
        "status": None,
        "pr_scope": make_pr_scope_record(
            user_decision="agent_failed", agent_errors=["launch refused"]
        ),
    }


def test_finalize_records_agent_errors_beside_recommendation() -> None:
    decision = finalize_pr_scope_decision(
        pr_scope=make_pr_scope_record(),
        user_decision="continue",
        gate_result={"gate": "pr-scope", "verdict": "atomic", "summary": "one change"},
        agent_errors=["codex familiar: invalid json"],
    )

    assert decision["pr_scope"]["verdict"] == "atomic"
    assert decision["pr_scope"]["agent_errors"] == ["codex familiar: invalid json"]


@pytest.mark.parametrize("errors", [[" "], [""], "launch refused", [3]])
def test_persist_rejects_blank_agent_error(tmp_path, errors: object) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"status":"running","history":[]}\n', encoding="utf-8")

    with pytest.raises(PrScopeStepError, match="agent_errors"):
        persist_pr_scope_outcome(
            state_path=state_path,
            pr_scope_path=tmp_path / "pr-scope.json",
            outcome={
                "status": None,
                "pr_scope": make_pr_scope_record(user_decision="agent_failed", agent_errors=errors),
            },
        )


@pytest.mark.parametrize("decision", ["declined_agent", "agent_failed"])
def test_finalize_drops_resumed_verdict(decision: str) -> None:
    planned = plan_pr_scope_step(
        pr_scope_mode="true",
        threshold=1000,
        existing_pr_scope=make_pr_scope_record(
            new_loc_total=282, verdict="under_threshold", summary="old"
        ),
        pr_scope_file_exists=True,
    )
    assert planned["action"] == "prompt"
    assert planned["pr_scope"]["verdict"] == "under_threshold"

    decision_record = finalize_pr_scope_decision(
        pr_scope=planned["pr_scope"], user_decision=decision
    )["pr_scope"]

    assert "verdict" not in decision_record
    assert "summary" not in decision_record
    assert decision_record["user_decision"] == decision


def test_persist_agent_failed_record_matches_state_schema(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"status":"running","history":[]}\n', encoding="utf-8")
    outcome = finalize_pr_scope_decision(
        pr_scope=make_pr_scope_record(),
        user_decision="agent_failed",
        agent_errors=["launch refused"],
    )

    updated_state = persist_pr_scope_outcome(
        state_path=state_path, pr_scope_path=tmp_path / "pr-scope.json", outcome=outcome
    )

    schema_path = Path(__file__).resolve().parents[2] / "templates" / "state.schema.json"
    pr_scope_schema = json.loads(schema_path.read_text())["properties"]["pr_scope"]
    errors = list(Draft202012Validator(pr_scope_schema).iter_errors(updated_state["pr_scope"]))
    assert not errors, [error.message for error in errors]


def test_finalize_pr_scope_decision_records_declined_agent() -> None:
    decision = finalize_pr_scope_decision(
        pr_scope=make_pr_scope_record(),
        user_decision="declined_agent",
    )

    assert decision == {
        "status": None,
        "pr_scope": make_pr_scope_record(user_decision="declined_agent"),
    }


def test_finalize_pr_scope_decision_merges_request_split_continue() -> None:
    decision = finalize_pr_scope_decision(
        pr_scope=make_pr_scope_record(),
        gate_result=make_request_split_gate_result(),
        user_decision="continue",
    )

    assert decision == {
        "status": None,
        "pr_scope": make_pr_scope_record(
            verdict="request_split",
            summary="Split middleware from billing.",
            splits=[
                {
                    "name": "catalog-preview middleware",
                    "rationale": "Isolated feature.",
                    "files": ["apps/web/server/middleware/catalog-preview.ts"],
                    "estimated_new_loc": 410,
                }
            ],
            remaining_in_original=["docs/changelog.md"],
            user_decision="continue",
        ),
    }


def test_finalize_pr_scope_decision_rejects_invalid_request_split_gate() -> None:
    with pytest.raises(PrScopeStepError, match="non-empty 'splits' list"):
        finalize_pr_scope_decision(
            pr_scope=make_pr_scope_record(),
            gate_result={
                "gate": "pr-scope",
                "verdict": "request_split",
                "summary": "Split required.",
                "splits": [],
                "remaining_in_original": [],
            },
            user_decision="continue",
        )


def test_finalize_pr_scope_decision_merges_request_split_abort() -> None:
    decision = finalize_pr_scope_decision(
        pr_scope=make_pr_scope_record(),
        gate_result=make_request_split_gate_result(),
        user_decision="abort",
    )

    assert decision == {
        "status": "scope_split_recommended",
        "pr_scope": make_pr_scope_record(
            verdict="request_split",
            summary="Split middleware from billing.",
            splits=[
                {
                    "name": "catalog-preview middleware",
                    "rationale": "Isolated feature.",
                    "files": ["apps/web/server/middleware/catalog-preview.ts"],
                    "estimated_new_loc": 410,
                }
            ],
            remaining_in_original=["docs/changelog.md"],
            user_decision="abort",
        ),
    }


def test_finalize_pr_scope_decision_rejects_gate_result_without_gate_field() -> None:
    with pytest.raises(PrScopeStepError, match="gate_result.gate must equal"):
        finalize_pr_scope_decision(
            pr_scope=make_pr_scope_record(),
            gate_result={"verdict": "atomic", "summary": "One change."},
            user_decision="continue",
        )


def test_finalize_pr_scope_decision_rejects_invalid_gate_verdict() -> None:
    with pytest.raises(PrScopeStepError, match="gate_result.verdict"):
        finalize_pr_scope_decision(
            pr_scope=make_pr_scope_record(),
            gate_result={
                "gate": "pr-scope",
                "verdict": "bogus",
                "summary": "Not a valid verdict.",
            },
            user_decision="continue",
        )


@pytest.mark.parametrize("summary", [None, "", " "])
def test_finalize_pr_scope_decision_rejects_missing_or_blank_summary(
    summary: object,
) -> None:
    gate_result: dict[str, object] = {
        "gate": "pr-scope",
        "verdict": "atomic",
    }
    if summary is not None:
        gate_result["summary"] = summary

    with pytest.raises(PrScopeStepError, match="gate_result.summary"):
        finalize_pr_scope_decision(
            pr_scope=make_pr_scope_record(),
            gate_result=gate_result,
            user_decision="continue",
        )


def test_finalize_pr_scope_decision_rejects_invalid_atomic_gate_shape() -> None:
    with pytest.raises(PrScopeStepError, match="atomic payload"):
        finalize_pr_scope_decision(
            pr_scope=make_pr_scope_record(),
            gate_result={
                "gate": "pr-scope",
                "verdict": "atomic",
                "summary": "This is one coherent change.",
                "splits": [],
            },
            user_decision="continue",
        )


def test_finalize_pr_scope_decision_rejects_atomic_abort() -> None:
    with pytest.raises(PrScopeStepError, match="abort requires"):
        finalize_pr_scope_decision(
            pr_scope=make_pr_scope_record(),
            gate_result={
                "gate": "pr-scope",
                "verdict": "atomic",
                "summary": "This is one coherent change.",
            },
            user_decision="abort",
        )


def test_finalize_pr_scope_decision_rejects_continue_without_gate_result() -> None:
    with pytest.raises(PrScopeStepError, match="gate_result is required"):
        finalize_pr_scope_decision(
            pr_scope=make_pr_scope_record(excluded_paths=[]),
            user_decision="continue",
        )


def test_finalize_pr_scope_decision_clears_stale_split_fields_on_atomic_verdict() -> None:
    decision = finalize_pr_scope_decision(
        pr_scope={
            "threshold": 1000,
            "new_loc_total": 1248,
            "splits": [{"name": "old split"}],
            "remaining_in_original": ["docs/changelog.md"],
        },
        gate_result={
            "gate": "pr-scope",
            "verdict": "atomic",
            "summary": "This is one coherent change.",
        },
        user_decision="continue",
    )

    assert decision == {
        "status": None,
        "pr_scope": {
            "threshold": 1000,
            "new_loc_total": 1248,
            "verdict": "atomic",
            "summary": "This is one coherent change.",
            "user_decision": "continue",
        },
    }


def test_persist_pr_scope_outcome_writes_state_and_pr_scope_file(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    pr_scope_path = tmp_path / "pr-scope.json"
    state_path.write_text('{"status":"running","history":[]}\n', encoding="utf-8")

    updated_state = persist_pr_scope_outcome(
        state_path=state_path,
        pr_scope_path=pr_scope_path,
        outcome={
            "action": "continue",
            "pr_scope": {
                "threshold": 1000,
                "new_loc_total": 282,
                "per_file": [{"added": 180, "deleted": 0, "path": "src/feature/foo.ts"}],
                "excluded_paths": ["package-lock.json"],
                "verdict": "under_threshold",
                "user_decision": "not_prompted",
            },
        },
    )

    assert updated_state["pr_scope"]["user_decision"] == "not_prompted"
    assert pr_scope_path.exists()
    assert '"user_decision": "not_prompted"' in pr_scope_path.read_text(encoding="utf-8")
    state_payload = state_path.read_text(encoding="utf-8")
    assert '"pr_scope":{"excluded_paths":["package-lock.json"]' in state_payload
    assert "\n  " not in state_payload


def test_persist_pr_scope_outcome_persists_prompt_action(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    pr_scope_path = tmp_path / "pr-scope.json"
    state_path.write_text('{"status":"running","history":[]}\n', encoding="utf-8")
    pr_scope = {
        "threshold": 1000,
        "new_loc_total": 1248,
        "per_file": [{"added": 1248, "deleted": 0, "path": "scripts/pr_scope_step.py"}],
        "excluded_paths": [],
    }

    updated_state = persist_pr_scope_outcome(
        state_path=state_path,
        pr_scope_path=pr_scope_path,
        outcome={"action": "prompt", "pr_scope": pr_scope},
    )

    assert updated_state["status"] == "running"
    assert updated_state["pr_scope"] == pr_scope
    assert pr_scope_path.exists()
    assert '"new_loc_total": 1248' in pr_scope_path.read_text(encoding="utf-8")


def test_persist_pr_scope_outcome_skip_leaves_state_untouched(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    pr_scope_path = tmp_path / "pr-scope.json"
    original = '{"status":"running","history":[]}\n'
    state_path.write_text(original, encoding="utf-8")

    updated_state = persist_pr_scope_outcome(
        state_path=state_path,
        pr_scope_path=pr_scope_path,
        outcome={"action": "skip", "pr_scope": None},
    )

    assert updated_state == {"status": "running", "history": []}
    assert state_path.read_text(encoding="utf-8") == original
    assert not pr_scope_path.exists()


def test_persist_pr_scope_outcome_rejects_unknown_action(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    pr_scope_path = tmp_path / "pr-scope.json"
    state_path.write_text('{"status":"running","history":[]}\n', encoding="utf-8")

    with pytest.raises(PrScopeStepError, match="outcome.action must be one of"):
        persist_pr_scope_outcome(
            state_path=state_path,
            pr_scope_path=pr_scope_path,
            outcome={
                "action": "typo",
                "pr_scope": {
                    "threshold": 1000,
                    "new_loc_total": 282,
                    "verdict": "under_threshold",
                    "user_decision": "not_prompted",
                },
            },
        )


def test_persist_pr_scope_outcome_records_terminal_status(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    pr_scope_path = tmp_path / "pr-scope.json"
    state_path.write_text('{"status":"running","history":[]}\n', encoding="utf-8")

    updated_state = persist_pr_scope_outcome(
        state_path=state_path,
        pr_scope_path=pr_scope_path,
        outcome={
            "action": "terminal",
            "status": "scope_split_recommended",
            "pr_scope": {
                "threshold": 1000,
                "new_loc_total": 1248,
                "verdict": "request_split",
                "summary": "Split middleware from billing.",
                "user_decision": "abort",
            },
        },
    )

    assert updated_state["status"] == "scope_split_recommended"
    assert '"scope_split_recommended"' in state_path.read_text(encoding="utf-8")


def test_persist_pr_scope_outcome_leaves_state_unchanged_if_pr_scope_write_fails(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    original = '{"status":"running","history":[]}\n'
    state_path.write_text(original, encoding="utf-8")

    with pytest.raises(PrScopeStepError, match="failed to write pr_scope file"):
        persist_pr_scope_outcome(
            state_path=state_path,
            pr_scope_path=tmp_path / "missing-dir" / "pr-scope.json",
            outcome={
                "action": "continue",
                "pr_scope": {
                    "threshold": 1000,
                    "new_loc_total": 282,
                    "verdict": "under_threshold",
                    "user_decision": "not_prompted",
                },
            },
        )

    assert state_path.read_text(encoding="utf-8") == original


def test_persist_pr_scope_outcome_reports_pr_scope_replace_failure(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "state.json"
    pr_scope_path = tmp_path / "pr-scope.json"
    original = '{"status":"running","history":[]}\n'
    state_path.write_text(original, encoding="utf-8")

    original_replace = Path.replace

    def failing_replace(self: Path, target: Path) -> Path:
        if target == pr_scope_path:
            raise OSError("simulated pr_scope replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(PrScopeStepError, match="failed to write pr_scope file"):
        persist_pr_scope_outcome(
            state_path=state_path,
            pr_scope_path=pr_scope_path,
            outcome={
                "action": "continue",
                "pr_scope": {
                    "threshold": 1000,
                    "new_loc_total": 282,
                    "verdict": "under_threshold",
                    "user_decision": "not_prompted",
                },
            },
        )

    assert state_path.read_text(encoding="utf-8") == original
    assert not pr_scope_path.exists()


def test_persist_pr_scope_outcome_restores_state_if_pr_scope_replace_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "state.json"
    pr_scope_path = tmp_path / "pr-scope.json"
    original_state = '{"status":"running","history":[]}\n'
    state_path.write_text(original_state, encoding="utf-8")
    original_pr_scope = '{"threshold":1000,"new_loc_total":50}\n'
    pr_scope_path.write_text(original_pr_scope, encoding="utf-8")

    original_replace = Path.replace
    calls: list[tuple[Path, Path]] = []

    def failing_replace(self: Path, target: Path) -> Path:
        calls.append((self, target))
        if target == pr_scope_path:
            raise OSError("simulated pr_scope replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(PrScopeStepError, match="failed to write pr_scope file"):
        persist_pr_scope_outcome(
            state_path=state_path,
            pr_scope_path=pr_scope_path,
            outcome={
                "action": "continue",
                "pr_scope": {
                    "threshold": 1000,
                    "new_loc_total": 282,
                    "verdict": "under_threshold",
                    "user_decision": "not_prompted",
                },
            },
        )

    assert state_path.read_text(encoding="utf-8") == original_state
    assert pr_scope_path.read_text(encoding="utf-8") == original_pr_scope
    assert any(target == pr_scope_path for _, target in calls)
    assert any(target == state_path for _, target in calls)


def test_persist_pr_scope_outcome_reports_state_restore_failure(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "state.json"
    pr_scope_path = tmp_path / "pr-scope.json"
    original_state = '{"status":"running","history":[]}\n'
    state_path.write_text(original_state, encoding="utf-8")

    original_replace = Path.replace
    pr_scope_replace_failed = False

    def failing_replace(self: Path, target: Path) -> Path:
        nonlocal pr_scope_replace_failed
        if target == pr_scope_path:
            pr_scope_replace_failed = True
            raise OSError("simulated pr_scope replace failure")
        if target == state_path and pr_scope_replace_failed:
            raise OSError("simulated state restore failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(PrScopeStepError, match="failed to restore original state"):
        persist_pr_scope_outcome(
            state_path=state_path,
            pr_scope_path=pr_scope_path,
            outcome={
                "action": "continue",
                "pr_scope": {
                    "threshold": 1000,
                    "new_loc_total": 282,
                    "verdict": "under_threshold",
                    "user_decision": "not_prompted",
                },
            },
        )


def test_main_plan_outputs_under_threshold_outcome(tmp_path, capsys) -> None:
    stdout_path = tmp_path / "count.stdout"
    stderr_path = tmp_path / "count.stderr"
    stdout_path.write_text(COUNT_STDOUT, encoding="utf-8")
    stderr_path.write_text(COUNT_STDERR, encoding="utf-8")

    rc = _main(
        [
            "plan",
            "--pr-scope-mode",
            "auto",
            "--threshold",
            "1000",
            "--count-stdout-file",
            str(stdout_path),
            "--count-stderr-file",
            str(stderr_path),
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert '"action":"continue"' in out
    assert '"user_decision":"not_prompted"' in out


def test_main_finalize_outputs_request_split_abort(capsys) -> None:
    rc = _main(
        [
            "finalize",
            "--pr-scope-json",
            (
                '{"threshold":1000,"new_loc_total":1248,'
                '"per_file":[{"path":"apps/web/server/middleware/catalog-preview.ts",'
                '"added":410,"deleted":0},'
                '{"path":"docs/changelog.md","added":838,"deleted":0}],'
                '"excluded_paths":["pnpm-lock.yaml"]}'
            ),
            "--user-decision",
            "abort",
            "--gate-result-json",
            (
                '{"gate":"pr-scope","verdict":"request_split",'
                '"summary":"Split middleware from billing.",'
                '"splits":[{"name":"middleware","rationale":"Isolated.",'
                '"files":["apps/web/server/middleware/catalog-preview.ts"],'
                '"estimated_new_loc":410}],'
                '"remaining_in_original":["docs/changelog.md"]}'
            ),
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert '"status":"scope_split_recommended"' in out
    assert '"user_decision":"abort"' in out
    assert '"verdict":"request_split"' in out


def test_persist_pr_scope_outcome_raises_on_invalid_status(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"iteration":0,"max_iterations":5,"status":"running","history":[]}',
        encoding="utf-8",
    )

    with pytest.raises(PrScopeStepError, match="status must be one of"):
        persist_pr_scope_outcome(
            state_path=state_path,
            pr_scope_path=tmp_path / "pr-scope.json",
            outcome={
                "action": "terminal",
                "status": "not_a_real_status",
                "pr_scope": make_pr_scope_record(user_decision="abort", verdict="request_split"),
            },
        )


def test_main_persist_returns_2_on_invalid_status(tmp_path, capsys) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"iteration":0,"max_iterations":5,"status":"running","history":[]}',
        encoding="utf-8",
    )

    rc = _main(
        [
            "persist",
            "--state",
            str(state_path),
            "--pr-scope-path",
            str(tmp_path / "pr-scope.json"),
            "--outcome-json",
            (
                '{"action":"terminal","status":"not_a_real_status",'
                '"pr_scope":{"threshold":1000,"new_loc_total":1248}}'
            ),
        ]
    )

    assert rc == 2
    assert "pr_scope_step: status must be one of" in capsys.readouterr().err


def test_main_finalize_returns_2_on_malformed_gate_result_json(capsys) -> None:
    rc = _main(
        [
            "finalize",
            "--pr-scope-json",
            '{"threshold":1000,"new_loc_total":1248}',
            "--user-decision",
            "continue",
            "--gate-result-json",
            "{broken",
        ]
    )

    assert rc == 2
    assert "pr_scope_step: failed to parse gate_result JSON" in capsys.readouterr().err


def test_main_persist_updates_state_and_scope_files_with_long_basenames(tmp_path) -> None:
    state_path = tmp_path / ("s" * 248 + ".json")
    pr_scope_path = tmp_path / ("p" * 248 + ".json")
    state_path.write_text('{"status":"running","history":[]}\n', encoding="utf-8")

    rc = _main(
        [
            "persist",
            "--state",
            str(state_path),
            "--pr-scope-path",
            str(pr_scope_path),
            "--outcome-json",
            '{"action":"continue","pr_scope":{"threshold":1000,"new_loc_total":282,"verdict":"under_threshold","user_decision":"not_prompted"}}',
        ]
    )

    assert rc == 0
    assert '"pr_scope":{"new_loc_total":282' in state_path.read_text(encoding="utf-8")
    assert '"user_decision": "not_prompted"' in pr_scope_path.read_text(encoding="utf-8")


def test_main_persist_updates_state_and_pr_scope_files_for_prompt_action(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    pr_scope_path = tmp_path / "pr-scope.json"
    state_path.write_text('{"status":"running","history":[]}\n', encoding="utf-8")

    rc = _main(
        [
            "persist",
            "--state",
            str(state_path),
            "--pr-scope-path",
            str(pr_scope_path),
            "--outcome-json",
            (
                '{"action":"prompt","pr_scope":{"threshold":1000,"new_loc_total":1248,'
                '"per_file":[{"added":1248,"deleted":0,"path":"scripts/pr_scope_step.py"}],'
                '"excluded_paths":[]}}'
            ),
        ]
    )

    assert rc == 0
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["status"] == "running"
    assert state_payload["pr_scope"] == {
        "threshold": 1000,
        "new_loc_total": 1248,
        "per_file": [{"added": 1248, "deleted": 0, "path": "scripts/pr_scope_step.py"}],
        "excluded_paths": [],
    }
    assert '"new_loc_total": 1248' in pr_scope_path.read_text(encoding="utf-8")


_FINALIZE_PR_SCOPE_JSON = (
    '{"threshold":1000,"new_loc_total":1248,'
    '"per_file":[{"path":"apps/web/server/middleware/catalog-preview.ts",'
    '"added":410,"deleted":0},'
    '{"path":"docs/changelog.md","added":838,"deleted":0}],'
    '"excluded_paths":["pnpm-lock.yaml"]}'
)
_FINALIZE_GATE_RESULT_JSON = (
    '{"gate":"pr-scope","verdict":"request_split",'
    '"summary":"Split middleware from billing.",'
    '"splits":[{"name":"middleware","rationale":"Isolated.",'
    '"files":["apps/web/server/middleware/catalog-preview.ts"],'
    '"estimated_new_loc":410}],'
    '"remaining_in_original":["docs/changelog.md"]}'
)


def test_main_plan_accepts_existing_pr_scope_from_file(tmp_path, capsys) -> None:
    existing_path = tmp_path / "existing.json"
    existing_path.write_text(
        json.dumps(
            make_pr_scope_record(
                user_decision="continue",
                verdict="under_threshold",
            )
        ),
        encoding="utf-8",
    )

    rc = _main(
        [
            "plan",
            "--pr-scope-mode",
            "auto",
            "--threshold",
            "1000",
            "--existing-pr-scope-json-file",
            str(existing_path),
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert '"action":"continue"' in out


def test_main_plan_rejects_both_inline_and_file_existing_pr_scope(tmp_path, capsys) -> None:
    existing_path = tmp_path / "existing.json"
    existing_path.write_text(json.dumps(make_pr_scope_record()), encoding="utf-8")

    rc = _main(
        [
            "plan",
            "--pr-scope-mode",
            "auto",
            "--threshold",
            "1000",
            "--existing-pr-scope-json",
            json.dumps(make_pr_scope_record()),
            "--existing-pr-scope-json-file",
            str(existing_path),
        ]
    )

    assert rc == 2
    assert (
        "pr_scope_step: --existing-pr-scope-json and --existing-pr-scope-json-file "
        "are mutually exclusive"
    ) in capsys.readouterr().err


def test_main_plan_returns_2_on_missing_existing_pr_scope_file(tmp_path, capsys) -> None:
    rc = _main(
        [
            "plan",
            "--pr-scope-mode",
            "auto",
            "--threshold",
            "1000",
            "--existing-pr-scope-json-file",
            str(tmp_path / "missing.json"),
        ]
    )

    assert rc == 2
    assert "pr_scope_step: failed to read existing pr_scope JSON file" in capsys.readouterr().err


def test_main_finalize_accepts_pr_scope_and_gate_result_from_file(tmp_path, capsys) -> None:
    pr_scope_path = tmp_path / "pr-scope.json"
    pr_scope_path.write_text(_FINALIZE_PR_SCOPE_JSON, encoding="utf-8")
    gate_result_path = tmp_path / "gate.json"
    gate_result_path.write_text(_FINALIZE_GATE_RESULT_JSON, encoding="utf-8")

    rc = _main(
        [
            "finalize",
            "--pr-scope-json-file",
            str(pr_scope_path),
            "--user-decision",
            "abort",
            "--gate-result-json-file",
            str(gate_result_path),
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert '"status":"scope_split_recommended"' in out
    assert '"user_decision":"abort"' in out


def test_main_finalize_rejects_both_inline_and_file_pr_scope(tmp_path, capsys) -> None:
    pr_scope_path = tmp_path / "pr-scope.json"
    pr_scope_path.write_text(_FINALIZE_PR_SCOPE_JSON, encoding="utf-8")

    rc = _main(
        [
            "finalize",
            "--pr-scope-json",
            _FINALIZE_PR_SCOPE_JSON,
            "--pr-scope-json-file",
            str(pr_scope_path),
            "--user-decision",
            "declined_agent",
        ]
    )

    assert rc == 2
    assert (
        "pr_scope_step: --pr-scope-json and --pr-scope-json-file are mutually exclusive"
        in capsys.readouterr().err
    )


def test_main_finalize_rejects_both_inline_and_file_gate_result(tmp_path, capsys) -> None:
    gate_result_path = tmp_path / "gate.json"
    gate_result_path.write_text(_FINALIZE_GATE_RESULT_JSON, encoding="utf-8")

    rc = _main(
        [
            "finalize",
            "--pr-scope-json",
            _FINALIZE_PR_SCOPE_JSON,
            "--user-decision",
            "abort",
            "--gate-result-json",
            _FINALIZE_GATE_RESULT_JSON,
            "--gate-result-json-file",
            str(gate_result_path),
        ]
    )

    assert rc == 2
    assert (
        "pr_scope_step: --gate-result-json and --gate-result-json-file are mutually exclusive"
        in capsys.readouterr().err
    )


def test_main_finalize_returns_2_when_pr_scope_input_is_missing(capsys) -> None:
    rc = _main(
        [
            "finalize",
            "--user-decision",
            "declined_agent",
        ]
    )

    assert rc == 2
    assert (
        "pr_scope_step: one of --pr-scope-json or --pr-scope-json-file is required"
        in capsys.readouterr().err
    )


def test_main_persist_accepts_outcome_from_file(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    pr_scope_path = tmp_path / "pr-scope.json"
    state_path.write_text('{"status":"running","history":[]}\n', encoding="utf-8")
    outcome_path = tmp_path / "outcome.json"
    outcome_path.write_text(
        '{"action":"continue","pr_scope":{"threshold":1000,"new_loc_total":282,'
        '"verdict":"under_threshold","user_decision":"not_prompted"}}',
        encoding="utf-8",
    )

    rc = _main(
        [
            "persist",
            "--state",
            str(state_path),
            "--pr-scope-path",
            str(pr_scope_path),
            "--outcome-json-file",
            str(outcome_path),
        ]
    )

    assert rc == 0
    assert '"pr_scope":{"new_loc_total":282' in state_path.read_text(encoding="utf-8")
    assert '"user_decision": "not_prompted"' in pr_scope_path.read_text(encoding="utf-8")


def test_main_persist_rejects_both_inline_and_file_outcome(tmp_path, capsys) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"status":"running","history":[]}\n', encoding="utf-8")
    outcome_path = tmp_path / "outcome.json"
    outcome_path.write_text('{"action":"skip"}', encoding="utf-8")

    rc = _main(
        [
            "persist",
            "--state",
            str(state_path),
            "--pr-scope-path",
            str(tmp_path / "pr-scope.json"),
            "--outcome-json",
            '{"action":"skip"}',
            "--outcome-json-file",
            str(outcome_path),
        ]
    )

    assert rc == 2
    assert (
        "pr_scope_step: --outcome-json and --outcome-json-file are mutually exclusive"
        in capsys.readouterr().err
    )


def test_main_persist_returns_2_when_outcome_input_is_missing(tmp_path, capsys) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"status":"running","history":[]}\n', encoding="utf-8")

    rc = _main(
        [
            "persist",
            "--state",
            str(state_path),
            "--pr-scope-path",
            str(tmp_path / "pr-scope.json"),
        ]
    )

    assert rc == 2
    assert (
        "pr_scope_step: one of --outcome-json or --outcome-json-file is required"
        in capsys.readouterr().err
    )
