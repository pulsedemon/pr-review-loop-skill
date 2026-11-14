"""Tests for scripts.scenario_validation helpers."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from scenario_validation import (  # type: ignore[import-not-found]
    ValidationError,
    _main,
    extract_validation_status,
)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "scenario.md"
    path.write_text(textwrap.dedent(body).lstrip("\n"))
    return path


def test_extract_validation_status_only_returns_status_block(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        # Scenario

        **Status:** `manual_validated`

        ## Validation status

        **Status:** `design_only`
        **Missing evidence:** Add a real validation run.

        ## Notes

        Some trailing notes.
        """,
    )

    assert extract_validation_status(path) == "\n".join(
        [
            "## Validation status",
            "",
            "**Status:** `design_only`",
            "**Missing evidence:** Add a real validation run.",
        ]
    )


def test_extract_validation_status_errors_when_heading_missing(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        # Scenario

        No validation heading here.
        """,
    )

    with pytest.raises(ValidationError, match=r"missing '## Validation status' section"):
        extract_validation_status(path)


def test_cli_requires_section_arg(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        _main([])

    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert "--section" in captured.err
