"""Unit tests for scripts/regen_move_a1_enum.py.

Each test seeds an isolated tree under tmp_path. Five surfaces exercised:
  - manifests/move-a1-enum.yaml      (source)
  - templates/state.schema.json      (inline-array enum)
  - reviewers/output.schema.json     (multi-line enum)
  - SKILL.md                         (sentence in named region)
  - reviewers/tests.md               (sentence in named region)
  - reviewers/adversary.md           (sentence in named region)

The seeded prose surfaces are minimal but structurally identical to the real
ones so the generator's region/sentence regex anchors are real-world tested.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "regen_move_a1_enum.py"
GENERATOR_SPEC = importlib.util.spec_from_file_location("regen_move_a1_enum", GENERATOR)
assert GENERATOR_SPEC is not None
assert GENERATOR_SPEC.loader is not None
regen = importlib.util.module_from_spec(GENERATOR_SPEC)
GENERATOR_SPEC.loader.exec_module(regen)

VALUES = [
    "cross_fixture",
    "testid_unmounted",
    "conditional_unmounted",
    "missing_state_assertion",
    "describe_label_drift",
]


def _backticked(values: list[str]) -> str:
    return ", ".join(f"`{v}`" for v in values)


def _seed(tmp_path: Path, values: list[str] | None = None) -> dict[str, Path]:
    vals = values if values is not None else VALUES
    backticked = _backticked(vals)

    manifest = tmp_path / "manifests" / "move-a1-enum.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "move_a1_pattern:\n" + "".join(f"  - {v}\n" for v in vals),
    )

    state_schema = tmp_path / "templates" / "state.schema.json"
    state_schema.parent.mkdir(parents=True)
    state_schema.write_text(
        "{\n"
        '  "properties": {\n'
        '    "history": {\n'
        '      "items": {\n'
        '        "properties": {\n'
        '          "findings": {\n'
        '            "items": {\n'
        '              "properties": {\n'
        '                "move_a1_pattern": { "type": "string", "enum": ['
        + ", ".join(f'"{v}"' for v in vals)
        + "] }\n"
        "              }\n"
        "            }\n"
        "          }\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )

    out_schema = tmp_path / "reviewers" / "output.schema.json"
    out_schema.parent.mkdir(parents=True)
    enum_lines = ",\n".join(f'              "{v}"' for v in vals)
    out_schema.write_text(
        "{\n"
        '  "properties": {\n'
        '    "findings": {\n'
        '      "items": {\n'
        '        "properties": {\n'
        '          "move_a1_pattern": {\n'
        '            "type": "string",\n'
        '            "enum": [\n'
        f"{enum_lines}\n"
        "            ]\n"
        "          }\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )

    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "# Skill\n\n"
        "- **Move A.1 (assertion-vacuity audit)**, `tests` only: for each "
        "assertion, check whether it's syntactically determinable to be vacuous "
        "via one of five sub-mechanics (<!-- regen:move-a1-enum:start -->"
        f"{backticked}"
        "<!-- regen:move-a1-enum:end -->); set `move_a1_pattern` on each "
        "finding. See `reviewers/tests.md`.\n"
    )

    tests_md = tmp_path / "reviewers" / "tests.md"
    bullet_block = "".join(f"{i + 1}. **{v}**, definition for {v}.\n" for i, v in enumerate(vals))
    tests_md.write_text(
        "# tests reviewer\n\n"
        "## Procedure move A.1\n\n"
        f"{bullet_block}"
        "\n"
        "<!-- regen:move-a1-enum:start -->\n"
        "Additionally, set the top-level finding property `move_a1_pattern` to "
        f"one of {backticked}.\n"
        "<!-- regen:move-a1-enum:end -->\n"
    )

    adv_md = tmp_path / "reviewers" / "adversary.md"
    adv_md.write_text(
        "# adversary\n\n"
        "- **Move A.1, assertion-vacuity audit.** ... five sub-mechanics "
        "(<!-- regen:move-a1-enum:start -->"
        f"{backticked}"
        "<!-- regen:move-a1-enum:end -->). ...\n"
    )

    return {
        "manifest": manifest,
        "state_schema": state_schema,
        "out_schema": out_schema,
        "skill": skill,
        "tests_md": tests_md,
        "adv_md": adv_md,
    }


def _run(paths: dict[str, Path], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--manifest",
            str(paths["manifest"]),
            "--state-schema",
            str(paths["state_schema"]),
            "--out-schema",
            str(paths["out_schema"]),
            "--skill",
            str(paths["skill"]),
            "--tests-md",
            str(paths["tests_md"]),
            "--adv-md",
            str(paths["adv_md"]),
            *args,
        ],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def test_check_clean_tree_exits_zero(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 0, result.stderr


# Per-surface drift tests pin the stderr to NAME the drifted surface and
# NOT name any of the four siblings. A regression that flags every surface
# on a single-surface drift would only be caught by this stricter check.
#
# Each surface has a distinctive path fragment AND we check the diff
# header (the only stable per-surface marker, prose surfaces freely
# cross-reference each other in their bodies, so plain path tokens
# match too eagerly). The diff header `+++ <path> (regenerated)` is
# emitted exclusively for surfaces whose regen produced a non-empty
# diff; for surfaces that fail the bullet-label scan or out-of-region
# grep, we additionally search for surface-specific tail messages.
_SURFACE_TOKENS = {
    "state_schema": "templates/state.schema.json",
    "out_schema": "reviewers/output.schema.json",
    "skill": "/SKILL.md",
    "tests_md": "reviewers/tests.md",
    "adv_md": "reviewers/adversary.md",
}


def _assert_only_surface_named(stderr: str, surface: str) -> None:
    own_token = _SURFACE_TOKENS[surface]
    assert own_token in stderr, f"expected {own_token} in stderr:\n{stderr}"
    # Anchor on the diff-header form ("+++ <path> (regenerated)") OR a
    # bullet-scan / out-of-region sentinel line, these are the lines the
    # generator emits ABOUT a specific surface (cross-references inside
    # diff bodies don't follow these shapes).
    for other, token in _SURFACE_TOKENS.items():
        if other == surface:
            continue
        assert f"{token} (regenerated)" not in stderr, (
            f"unexpected sibling diff header for {other} ({token}) in:\n{stderr}"
        )


def test_check_drifted_state_schema_exits_five(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    text = paths["state_schema"].read_text().replace("cross_fixture", "xfoo", 1)
    paths["state_schema"].write_text(text)
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 5, result.stderr
    _assert_only_surface_named(result.stderr, "state_schema")


def test_check_drifted_out_schema_exits_five(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    text = paths["out_schema"].read_text().replace("describe_label_drift", "yfoo", 1)
    paths["out_schema"].write_text(text)
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 5, result.stderr
    _assert_only_surface_named(result.stderr, "out_schema")


def test_check_drifted_skill_exits_five(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    text = paths["skill"].read_text().replace("testid_unmounted", "zfoo", 1)
    paths["skill"].write_text(text)
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 5, result.stderr
    _assert_only_surface_named(result.stderr, "skill")


def test_check_drifted_tests_md_exits_five(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    text = paths["tests_md"].read_text()
    # Drift only the in-region occurrence (last one) so the bullet labels
    # outside the region remain consistent with the manifest. This
    # exercises the regen-diff path, not the bullet-label scan.
    idx = text.rfind("conditional_unmounted")
    drifted = text[:idx] + "afoo" + text[idx + len("conditional_unmounted") :]
    paths["tests_md"].write_text(drifted)
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 5, result.stderr
    _assert_only_surface_named(result.stderr, "tests_md")


def test_check_drifted_adv_md_exits_five(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    text = paths["adv_md"].read_text().replace("missing_state_assertion", "bfoo", 1)
    paths["adv_md"].write_text(text)
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 5, result.stderr
    _assert_only_surface_named(result.stderr, "adv_md")


def test_write_repairs_drift_across_all_surfaces(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    expected_prose = {key: paths[key].read_bytes() for key in ("skill", "tests_md", "adv_md")}
    paths["state_schema"].chmod(0o755)
    paths["state_schema"].write_text(
        paths["state_schema"].read_text().replace("cross_fixture", "xfoo", 1)
    )
    expected = (
        paths["out_schema"]
        .read_text()
        .replace('              "', '                 "')
        .replace("            ]", "               ]")
        .replace("\n", "\r")
        .encode()
    )
    paths["out_schema"].write_bytes(expected.replace(b"describe_label_drift", b"yfoo", 1))
    paths["skill"].write_text(paths["skill"].read_text().replace("testid_unmounted", "zfoo", 1))
    tests_text = paths["tests_md"].read_text()
    idx = tests_text.rfind("conditional_unmounted")
    paths["tests_md"].write_text(
        tests_text[:idx] + "afoo" + tests_text[idx + len("conditional_unmounted") :]
    )
    paths["adv_md"].write_text(
        paths["adv_md"].read_text().replace("missing_state_assertion", "bfoo", 1)
    )

    write = _run(paths, "--write", "--out-of-region-root", str(tmp_path))
    assert write.returncode == 0, write.stderr
    assert paths["state_schema"].stat().st_mode & 0o7777 == 0o755
    for key, original in expected_prose.items():
        assert paths[key].read_bytes() == original
    assert paths["out_schema"].read_bytes() == expected
    state = json.loads(paths["state_schema"].read_text())
    assert (
        state["properties"]["history"]["items"]["properties"]["findings"]["items"]["properties"][
            "move_a1_pattern"
        ]["enum"]
        == VALUES
    )

    check = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert check.returncode == 0, check.stderr


def test_out_of_region_occurrence_in_sibling_file_exits_five(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _seed(tmp_path)
    stray = tmp_path / "docs" / "stray.md"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text("ā mentions cross_fixture without a region marker.\n", encoding="utf-8")
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setenv("PYTHONCOERCECLOCALE", "0")
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 5
    assert "stray.md:1: ā mentions" in result.stderr, result.stderr


def test_out_of_region_scan_rejects_undecodable_text_and_skips_binary(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    source = tmp_path / "stray.md"
    source.write_bytes(b"caf\xe9 cross_fixture")
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 3
    assert f"cannot scan {source}" in result.stderr
    source.write_bytes(b"\x00cross_fixture")
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 5 and str(source) in result.stderr
    source.write_bytes(b"\x00\xffcross_fixture")
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 3 and str(source) in result.stderr
    source.rename(tmp_path / "asset.bin")
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("suffix", "data"),
    [
        ("txt", "future cross_fixture mirror".encode("utf-16le")),
        ("py", "café cross_fixture".encode("utf-16le")),
        ("yml", "café cross_fixture".encode("utf-16le")),
        ("txt", "café cross_fixture".encode("utf-16le")),
        ("txt", "cross_fixture".encode("utf-16")),
        ("txt", b"\xef\xbb\xbf\x00\xffcross_fixture"),
    ],
)
def test_scan_reports_undecodable_plain_text(tmp_path: Path, suffix: str, data: bytes) -> None:
    paths = _seed(tmp_path)
    notes = tmp_path / f"notes\nnext.{suffix}"
    notes.write_bytes(data)
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 3
    assert f"cannot scan {tmp_path}/notes\\nnext.{suffix}" in result.stderr


def test_missing_scan_root_reports_incomplete_discovery_after_mirror_drift(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    mirror = paths["out_schema"]
    mirror.write_text(mirror.read_text().replace("describe_label_drift", "stale_label", 1))
    missing = tmp_path / "missing"
    result = _run(paths, "--check", "--out-of-region-root", str(missing))
    assert result.returncode == 3
    assert f"--- {mirror}\n" in result.stderr
    assert "stale_label" in result.stderr
    assert f"cannot scan {missing}" in result.stderr


def test_discovery_read_error_names_the_file(tmp_path: Path, monkeypatch, capsys) -> None:
    source = tmp_path / "source.md"
    source.write_text("ordinary prose")
    read = Path.read_bytes

    def fail_read(path):
        if path == source:
            raise PermissionError("read denied")
        return read(path)

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(SystemExit) as error:
        regen._scan_out_of_region(tmp_path, ["value"], tmp_path / "manifest.yaml", [])
    assert error.value.code == 3
    assert f"cannot scan {source}: read denied" in capsys.readouterr().err


def test_out_of_region_scan_ignores_nested_worktrees(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    for worktree_dir in (".worktrees", "worktrees"):
        nested = tmp_path / worktree_dir / "manual-scenario-validation" / "SKILL.md"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text(
            "Nested worktree mirror mentions `cross_fixture`, `testid_unmounted`, "
            "`conditional_unmounted`, `missing_state_assertion`, and "
            "`describe_label_drift`.\n"
        )

    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))

    assert result.returncode == 0, result.stderr


def test_out_of_region_scan_prunes_excluded_trees(tmp_path: Path, monkeypatch) -> None:
    paths = _seed(tmp_path)
    nested = tmp_path / ".worktrees" / "manual-scenario-validation" / "SKILL.md"
    nested.parent.mkdir(parents=True, exist_ok=True)
    nested.write_text("Nested mirror mentions cross_fixture.\n")

    def fail_rglob(self: Path, pattern: str) -> object:
        raise AssertionError("out-of-region scan must prune with os.walk, not Path.rglob")

    monkeypatch.setattr(Path, "rglob", fail_rglob)

    hits = regen._scan_out_of_region(
        tmp_path,
        VALUES,
        paths["manifest"],
        [
            paths["state_schema"],
            paths["out_schema"],
            paths["skill"],
            paths["tests_md"],
            paths["adv_md"],
        ],
    )

    assert hits == []


def test_missing_manifest_exits_three(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    paths["manifest"].unlink()
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 3, result.stderr


def test_bare_string_manifest_exits_three(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    paths["manifest"].write_text("move_a1_pattern: abc\n")
    result = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert result.returncode == 3
    assert "must be a non-empty list of strings" in result.stderr


def test_write_propagates_new_value_to_all_surfaces(tmp_path: Path) -> None:
    paths = _seed(tmp_path)
    new_values = [*VALUES[:-1], "renamed_pattern"]
    paths["manifest"].write_text("move_a1_pattern:\n" + "".join(f"  - {v}\n" for v in new_values))
    write = _run(paths, "--write", "--out-of-region-root", str(tmp_path))
    assert write.returncode == 0, write.stderr

    state_text = paths["state_schema"].read_text()
    out_text = paths["out_schema"].read_text()
    skill_text = paths["skill"].read_text()
    tests_text = paths["tests_md"].read_text()
    adv_text = paths["adv_md"].read_text()
    for v in new_values:
        assert v in state_text
        assert v in out_text
        assert v in skill_text
        assert v in tests_text
        assert v in adv_text
    assert "describe_label_drift" not in state_text
    assert "describe_label_drift" not in out_text

    state_data = json.loads(state_text)
    enum = state_data["properties"]["history"]["items"]["properties"]["findings"]["items"][
        "properties"
    ]["move_a1_pattern"]["enum"]
    assert enum == new_values
    out_data = json.loads(out_text)
    out_enum = out_data["properties"]["findings"]["items"]["properties"]["move_a1_pattern"]["enum"]
    assert out_enum == new_values


def test_rename_leaves_bullet_label_stale_and_caught_by_check(tmp_path: Path) -> None:
    """Regression: when a manifest value is renamed, the future-mirror /
    bullet-label scan must catch the stale name in reviewers/tests.md
    bullet definitions (which sit OUTSIDE the named region).

    Sequence:
      1. Seed clean tree.
      2. Rename cross_fixture -> cross_fixture_v2 in manifest.
      3. Run --write: schemas, SKILL.md, tests.md in-region sentence,
         and adversary.md all update; the bullet definition
         "1. **cross_fixture**, ..." is intentionally not rewritten
         (region-scoped surgery, by design).
      4. Run --check: must exit 5 because **cross_fixture** is now a
         stale bullet label outside the named region.
    """
    paths = _seed(tmp_path)
    paths["manifest"].write_text(
        "move_a1_pattern:\n"
        "  - cross_fixture_v2\n"
        "  - testid_unmounted\n"
        "  - conditional_unmounted\n"
        "  - missing_state_assertion\n"
        "  - describe_label_drift\n"
    )
    write = _run(paths, "--write", "--out-of-region-root", str(tmp_path))
    assert write.returncode == 0, write.stderr

    check = _run(paths, "--check", "--out-of-region-root", str(tmp_path))
    assert check.returncode == 5, check.stderr
    assert "reviewers/tests.md" in check.stderr, check.stderr
    assert "cross_fixture" in check.stderr, check.stderr


def test_missing_skill_region_is_allowed_when_optional(tmp_path: Path) -> None:
    """SKILL.md may legitimately carry no region.

    Its region sits inside the generated §4b Move A.1 bullet, which cog
    omits when no persona sets `move_a1`. Treating that as fatal made the
    documented no-carrier state unregenerable: `scripts/regen.sh` runs cog
    first, then this generator, so it aborted on cog's own correct output.
    """
    text = "no region here\n"
    assert regen._regen_prose(text, tmp_path / "SKILL.md", VALUES, optional=True) == text


def test_missing_region_still_fatal_for_the_hand_written_mirrors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """reviewers/tests.md and adversary.md always carry the region."""
    with pytest.raises(SystemExit) as exc_info:
        regen._regen_prose("no region here\n", tmp_path / "tests.md", VALUES)
    assert exc_info.value.code == 3
    assert "no regen:move-a1-enum region found" in capsys.readouterr().err
