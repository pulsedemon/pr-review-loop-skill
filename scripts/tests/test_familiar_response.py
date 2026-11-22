"""Tests for scripts/familiar_response.py, which pulls the reply object out of a
Witch familiar report before the existing validators read it."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from familiar_response import last_object

SCRIPT = Path(__file__).resolve().parents[1] / "familiar_response.py"
REVIEW = {"reviewer": "tests", "verdict": "approve", "findings": []}
REVIEW_TEXT = json.dumps(REVIEW)


def test_bare_object():
    assert last_object(REVIEW_TEXT) == REVIEW


def test_prose_before_object():
    assert last_object(f"checking the diff now.\n{REVIEW_TEXT}\n") == REVIEW


def test_fenced_rejected():
    assert last_object(f"```json\n{REVIEW_TEXT}\n```\n") is None
    assert last_object(f"```json\n{REVIEW_TEXT}\n") is None


def test_last_of_several():
    final = {"reviewer": "b", "verdict": "comment", "findings": [{"summary": "s"}]}
    text = '{"x": 1}\n\nprogress\n' + json.dumps(final)
    assert last_object(text) == final


def test_trailing_witch_lines():
    denied = f"{REVIEW_TEXT}\nPermission denied: Bash  x  $ gh pr view\n"
    suspended = (
        f"{REVIEW_TEXT}\n\nThis run was suspended for 4m of its 9m, as when the Mac sleeps, "
        "so its elapsed time overstates its work."
    )
    assert last_object(denied) == REVIEW
    assert last_object(suspended) == REVIEW


def test_pretty_printed():
    assert last_object("done.\n" + json.dumps(REVIEW, indent=2)) == REVIEW


def test_array_wrapped():
    assert last_object(f"[{REVIEW_TEXT}]") is None
    assert last_object(json.dumps([REVIEW], indent=2)) is None


def test_text_after_object():
    assert last_object(f"{REVIEW_TEXT}\nmore prose") is None


def test_no_object(tmp_path):
    report = tmp_path / "report.md"
    report.write_text("no json here {")
    assert last_object(report.read_text()) is None
    result = subprocess.run([sys.executable, SCRIPT, report], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stdout == ""


def test_cli_prints_object(tmp_path):
    report = tmp_path / "report.md"
    report.write_text(f"reviewing.\n{json.dumps(REVIEW, indent=2)}\n")
    result = subprocess.run([sys.executable, SCRIPT, report], capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout) == REVIEW
