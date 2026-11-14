"""Tests for scripts.scenario_manifest — the scenario manifest loader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from scenario_manifest import (  # type: ignore[import-not-found]
    Manifest,
    ManifestError,
    Scenario,
    _main,
    load_manifest,
)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "manifest.yaml"
    path.write_text(textwrap.dedent(body).lstrip("\n"))
    return path


_MINIMAL_VALID = """
scenarios:
  - number: 1
    file: 01-approval-pressure.md
    title: Approval pressure
    tier: manual_validated
    reason: Recorded manual validation exists in the scenario file.
"""


def test_load_real_manifest_succeeds() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = load_manifest(repo_root / "tests" / "scenarios" / "manifest.yaml")
    scenario_files = sorted(path.name for path in (repo_root / "tests" / "scenarios").glob("*.md"))
    assert isinstance(manifest, Manifest)
    assert [scenario.file for scenario in manifest.scenarios] == scenario_files
    assert manifest.by_number(1).file == "01-approval-pressure.md"


def test_ci_trusted_requires_proof_sources(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        scenarios:
          - number: 11
            file: 11-count-new-loc-streams.md
            title: count_new_loc stream separation
            tier: ci_trusted
            reason: Covered by bats.
        """,
    )
    with pytest.raises(ManifestError, match=r"ci_trusted scenarios must define proof_sources"):
        load_manifest(path)


def test_duplicate_numbers_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        scenarios:
          - number: 1
            file: 01-approval-pressure.md
            title: Approval pressure
            tier: manual_validated
            reason: Recorded manual validation exists in the scenario file.
          - number: 1
            file: 01-ci-out-of-scope.md
            title: CI failure looks out of scope
            tier: manual_validated
            reason: Recorded manual validation exists in the scenario file.
        """,
    )
    with pytest.raises(ManifestError, match=r"duplicate scenario number: 1"):
        load_manifest(path)


def test_non_ci_trusted_may_not_define_proof_sources(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        scenarios:
          - number: 1
            file: 01-approval-pressure.md
            title: Approval pressure
            tier: manual_validated
            reason: Recorded manual validation exists in the scenario file.
            proof_sources:
              - tests/bats/fictional-proof.bats
        """,
    )
    with pytest.raises(ManifestError, match=r"only ci_trusted scenarios may define proof_sources"):
        load_manifest(path)


def test_file_must_match_number_prefix(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        scenarios:
          - number: 7
            file: 08-pr-scope-over-threshold.md
            title: PR-scope check, under threshold
            tier: design_only
            reason: Still only specified as a manual orchestration contract.
        """,
    )
    with pytest.raises(
        ManifestError, match=r"file '08-pr-scope-over-threshold\.md' must start with '07-'"
    ):
        load_manifest(path)


def test_sorted_number_order_required(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        scenarios:
          - number: 2
            file: 02-ci-out-of-scope.md
            title: CI failure looks out of scope
            tier: manual_validated
            reason: Recorded manual validation exists in the scenario file.
          - number: 1
            file: 01-approval-pressure.md
            title: Approval pressure
            tier: manual_validated
            reason: Recorded manual validation exists in the scenario file.
        """,
    )
    with pytest.raises(ManifestError, match=r"scenario numbers must be strictly increasing"):
        load_manifest(path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            """
            scenarios:
              - 123
            """,
            r"must be a mapping",
        ),
        (
            """
            scenarios:
              - number: 1
                file: 01-approval-pressure.md
                title: Approval pressure
                tier: manual_validated
            """,
            r"missing required key\(s\): reason",
        ),
        (
            """
            scenarios:
              - number: 1
                file: 01-approval-pressure.md
                title: Approval pressure
                tier: manual_validated
                reason: Recorded manual validation exists in the scenario file.
                extra: nope
            """,
            r"unknown key\(s\): extra",
        ),
        (
            """
            scenarios:
              - number: "1"
                file: 01-approval-pressure.md
                title: Approval pressure
                tier: manual_validated
                reason: Recorded manual validation exists in the scenario file.
            """,
            r"\.number must be an integer",
        ),
        (
            """
            scenarios:
              - number: 1
                file: 123
                title: Approval pressure
                tier: manual_validated
                reason: Recorded manual validation exists in the scenario file.
            """,
            r"\.file must be a string",
        ),
        (
            """
            scenarios:
              - number: 1
                file: 01-approval-pressure.md
                title: 123
                tier: manual_validated
                reason: Recorded manual validation exists in the scenario file.
            """,
            r"\.title must be a string",
        ),
        (
            """
            scenarios:
              - number: 1
                file: 01-approval-pressure.md
                title: Approval pressure
                tier: 123
                reason: Recorded manual validation exists in the scenario file.
            """,
            r"\.tier must be a string",
        ),
        (
            """
            scenarios:
              - number: 1
                file: 01-approval-pressure.md
                title: Approval pressure
                tier: manual_validated
                reason: 123
            """,
            r"\.reason must be a string",
        ),
        (
            """
            scenarios:
              - number: 11
                file: 11-count-new-loc-streams.md
                title: count_new_loc stream separation
                tier: ci_trusted
                reason: Covered by bats.
                proof_sources: tests/bats/count_new_loc.bats
            """,
            r"\.proof_sources must be a list",
        ),
        (
            """
            scenarios:
              - number: 11
                file: 11-count-new-loc-streams.md
                title: count_new_loc stream separation
                tier: ci_trusted
                reason: Covered by bats.
                proof_sources:
                  - 123
            """,
            r"\.proof_sources\[0\] must be a string",
        ),
    ],
)
def test_invalid_row_shapes_are_rejected(tmp_path: Path, body: str, message: str) -> None:
    path = _write(tmp_path, body)
    with pytest.raises(ManifestError, match=message):
        load_manifest(path)


def test_by_tier_filters_expected_scenarios(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        scenarios:
          - number: 1
            file: 01-approval-pressure.md
            title: Approval pressure
            tier: manual_validated
            reason: Recorded manual validation exists in the scenario file.
          - number: 11
            file: 11-count-new-loc-streams.md
            title: count_new_loc stream separation
            tier: ci_trusted
            reason: Covered by bats.
            proof_sources:
              - tests/bats/count_new_loc.bats
          - number: 13
            file: 13-adversary-catches-panel-miss.md
            title: Adversary catches panel miss
            tier: design_only
            reason: Still manual-only because adversary behavior is non-deterministic.
        """,
    )
    manifest = load_manifest(path)
    assert [scenario.file for scenario in manifest.by_tier("ci_trusted")] == [
        "11-count-new-loc-streams.md"
    ]
    assert [scenario.file for scenario in manifest.by_tier("manual_validated")] == [
        "01-approval-pressure.md"
    ]
    assert [scenario.file for scenario in manifest.by_tier("design_only")] == [
        "13-adversary-catches-panel-miss.md"
    ]


@pytest.mark.parametrize(
    ("list_name", "expected_output"),
    [
        ("all-files", "01-approval-pressure.md\n11-count-new-loc-streams.md"),
        ("ci-files", "11-count-new-loc-streams.md"),
        ("manual-files", "01-approval-pressure.md"),
        (
            "tier-map",
            "01-approval-pressure.md|manual_validated\n11-count-new-loc-streams.md|ci_trusted",
        ),
    ],
)
def test_cli_lists_requested_views(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    list_name: str,
    expected_output: str,
) -> None:
    path = _write(
        tmp_path,
        """
        scenarios:
          - number: 1
            file: 01-approval-pressure.md
            title: Approval pressure
            tier: manual_validated
            reason: Recorded manual validation exists in the scenario file.
          - number: 11
            file: 11-count-new-loc-streams.md
            title: count_new_loc stream separation
            tier: ci_trusted
            reason: Covered by bats.
            proof_sources:
              - tests/bats/count_new_loc.bats
        """,
    )
    status = _main(["--manifest", str(path), "--list", list_name])
    captured = capsys.readouterr()
    assert status == 0
    assert captured.out.strip() == expected_output


def test_cli_proof_sources_requires_ci_trusted_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, _MINIMAL_VALID)
    status = _main(["--manifest", str(path), "--proof-sources-for", "01-approval-pressure.md"])
    captured = capsys.readouterr()
    assert status == 4
    assert "is not ci_trusted" in captured.err


def test_proof_sources_reject_repo_escape(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        scenarios:
          - number: 11
            file: 11-count-new-loc-streams.md
            title: count_new_loc stream separation
            tier: ci_trusted
            reason: Covered by bats.
            proof_sources:
              - ../../outside.txt
        """,
    )
    with pytest.raises(ManifestError, match=r"must stay within the repo root"):
        load_manifest(path)


def test_proof_sources_reject_absolute_paths(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        scenarios:
          - number: 11
            file: 11-count-new-loc-streams.md
            title: count_new_loc stream separation
            tier: ci_trusted
            reason: Covered by bats.
            proof_sources:
              - /tmp/proof.txt
        """,
    )
    with pytest.raises(ManifestError, match=r"must be repo-relative"):
        load_manifest(path)


def test_load_manifest_returns_scenario_instances(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        scenarios:
          - number: 11
            file: 11-count-new-loc-streams.md
            title: count_new_loc stream separation
            tier: ci_trusted
            reason: Covered by bats.
            proof_sources:
              - tests/bats/count_new_loc.bats
        """,
    )
    manifest = load_manifest(path)
    assert manifest.scenarios == (
        Scenario(
            number=11,
            file="11-count-new-loc-streams.md",
            title="count_new_loc stream separation",
            tier="ci_trusted",
            reason="Covered by bats.",
            proof_sources=("tests/bats/count_new_loc.bats",),
        ),
    )
