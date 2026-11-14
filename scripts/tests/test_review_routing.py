"""Regression coverage across promotion, gate validation, and panel selection."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
FINDING = {
    "reviewer": "tests",
    "source_reviewers": ["tests"],
    "severity": "suggestion",
    "scope": "in_scope",
    "file": "src/parser.py",
    "line": 10,
    "summary": "parser cache retains stale tokens",
    "detail": "cache invalidation concern",
}
PROMOTION_KNOBS = {
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": True,
    "adversary_solo_promotion": True,
    "demoted": [],
}


def run_script(name, payload, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
    )


def test_promoted_suggestion_owners_cannot_be_skipped_by_delta_gates():
    promotion = run_script(
        "promote_findings.py",
        {**PROMOTION_KNOBS, "findings": [{**FINDING, "source_reviewers": ["tests", "security"]}]},
    )
    assert promotion.returncode == 0, promotion.stderr
    partitions = json.loads(promotion.stdout)
    panel = ["correctness", "tests", "security"]
    selection = run_script(
        "select_panel.py",
        {
            "panel": panel,
            "iteration": 2,
            "delta_gate": True,
            "delta_gate_min_candidates": 1,
            "prev_history": {
                "findings": partitions["blockers"],
                "addressed": partitions["addressed"],
            },
            "gate_results": [
                {"reviewer": name, "relevant": False, "reason": "unrelated delta"} for name in panel
            ],
        },
    )
    assert selection.returncode == 0, selection.stderr
    output = json.loads(selection.stdout)
    assert output["ran"] == ["tests", "security"]
    assert output["open_blocker_carryover"] == ["tests", "security"]
    assert output["skipped"] == ["correctness"]


@pytest.mark.parametrize("panel_scope", ["in_scope", "out_of_scope"])
def test_scope_disagreement_preserves_deferral_and_actionable_finding(panel_scope):
    adversary_scope = "out_of_scope" if panel_scope == "in_scope" else "in_scope"
    result = run_script(
        "promote_findings.py",
        {
            **PROMOTION_KNOBS,
            "panel_findings": [{**FINDING, "scope": panel_scope}],
            "adversary_findings": [
                {
                    **FINDING,
                    "reviewer": "adversary",
                    "source_reviewers": ["adversary"],
                    "severity": "blocker",
                    "scope": adversary_scope,
                }
            ],
        },
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert len(output["deferred"]) == 1
    if panel_scope == "in_scope":
        assert output["blockers"] == []
        assert output["suggestions"] == [FINDING]
    else:
        assert output["suggestions"] == []
        assert len(output["blockers"]) == 1
        assert output["blockers"][0]["source_reviewers"] == ["adversary"]


def test_wrong_identity_gate_cannot_replace_a_missing_gate():
    gate = {"reviewer": "security", "relevant": False, "reason": "no relevant changes"}
    validation = run_script("validate_gate_output.py", gate, "--reviewer", "correctness")
    assert validation.returncode == 2
    assert "expected reviewer 'correctness'" in validation.stderr
    selection = run_script(
        "select_panel.py",
        {
            "panel": ["correctness", "security"],
            "iteration": 2,
            "delta_gate": True,
            "delta_gate_min_candidates": 1,
            "prev_history": {"findings": []},
            "gate_results": [gate] if validation.returncode == 0 else [],
        },
    )
    assert selection.returncode == 0, selection.stderr
    output = json.loads(selection.stdout)
    assert output["ran"] == ["correctness", "security"]
    assert output["gate_fail_open"] == ["correctness", "security"]
    assert output["skipped"] == []


def test_matching_dispatched_gate_identity_passes():
    gate = {"reviewer": "security", "relevant": False, "reason": "no relevant changes"}
    result = run_script("validate_gate_output.py", gate, "--reviewer", "security")
    assert result.returncode == 0, result.stderr
