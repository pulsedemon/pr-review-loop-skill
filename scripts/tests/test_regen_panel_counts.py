"""tests for generated panel-count phrases."""

from __future__ import annotations

from pathlib import Path

import pytest
import regen_panel_counts  # type: ignore[import-not-found]  # sibling module made importable by conftest.py


def _write_manifest(
    tmp_path: Path, panel_names: list[str], adversary_name: str = "adversary"
) -> Path:
    lines = ["panel:"]
    for i, name in enumerate(panel_names):
        owns = "true" if i == 0 else "false"
        lines.append(f"  - name: {name}")
        lines.append(f"    file: {name}.md")
        lines.append(f"    description: {name} persona")
        lines.append(f"    owns_schema_constraint_blocker: {owns}")
    lines.append("adversary:")
    lines.append(f"  name: {adversary_name}")
    lines.append(f"  file: {adversary_name}.md")
    lines.append(f"  description: {adversary_name} persona")
    lines.append("addendums: []")
    p = tmp_path / "personas.yaml"
    p.write_text("\n".join(lines) + "\n")
    return p


def _make_corpus(tmp_path: Path) -> Path:
    """Lay out a minimal corpus tree the generator will scan."""
    root = tmp_path / "corpus"
    (root / "tests" / "scenarios").mkdir(parents=True)
    (root / "reviewers").mkdir(parents=True)
    return root


def _run(args: list[str]) -> int:
    return regen_panel_counts.main(args)


def _total_region(template: str, rendered: str) -> str:
    return (
        "<!-- regen:panel-count-total:start -->\n"
        f"<!-- template: {template} -->\n"
        f"{rendered}\n"
        "<!-- regen:panel-count-total:end -->\n"
    )


def _total_plus_1_region(template: str, rendered: str) -> str:
    return (
        "<!-- regen:panel-count-total-plus-1:start -->\n"
        f"<!-- template: {template} -->\n"
        f"{rendered}\n"
        "<!-- regen:panel-count-total-plus-1:end -->\n"
    )


def test_check_returns_0_on_clean_tree(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, ["a", "b", "c", "d", "e"])  # n = 5
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        "Heading\n\n"
        + _total_region("the panel of {n} {personas|persona}", "the panel of 5 personas")
        + "\nmore text\n"
        + _total_plus_1_region(
            "{n} personas total (panel + adversary)", "6 personas total (panel + adversary)"
        )
    )
    rc = _run(
        ["--check", "--manifest", str(manifest), "--corpus-root", str(root)],
    )
    assert rc == 0


def test_check_returns_5_on_drift_in_any_one_surface(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _write_manifest(tmp_path, ["a", "b", "c"])  # n = 3
    root = _make_corpus(tmp_path)
    drifted = (
        "<!-- regen:panel-count-total:start -->\n"
        "<!-- template: the panel of {n} {personas|persona} -->\n"
        "the panel of 99 personas\n"  # drifted: should be 3
        "<!-- regen:panel-count-total:end -->\n"
    )
    (root / "reviewers" / "alpha.md").write_text(drifted)
    rc = _run(["--check", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == regen_panel_counts._DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "alpha.md" in err
    assert "regen.sh" in err


def test_write_repairs_drift_across_all_surfaces(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, ["a", "b", "c", "d"])  # n = 4
    root = _make_corpus(tmp_path)
    skill = root / "SKILL.md"
    scen = root / "tests" / "scenarios" / "01.md"
    rev = root / "reviewers" / "alpha.md"
    skill.write_text(
        _total_region("panel of {n} reviewer {personas|persona}", "panel of 99 reviewer personas")
    )
    scen.write_text(
        _total_plus_1_region(
            "{n} personas total (panel + adversary)", "1 personas total (panel + adversary)"
        )
    )
    rev.write_text(
        _total_region(
            "the other {n} {personas|persona}",
            "the other 0 personas",
        )
    )
    skill.chmod(0o755)
    rc = _run(["--write", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0
    assert skill.stat().st_mode & 0o7777 == 0o755
    assert "panel of 4 reviewer personas" in skill.read_text()
    assert "5 personas total (panel + adversary)" in scen.read_text()
    assert "the other 4 personas" in rev.read_text()
    rc = _run(["--check", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0


def test_plural_agreement_n_equals_1(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, ["solo"])  # n = 1
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        _total_region("the panel of {n} {personas|persona}", "the panel of 1 persona")
    )
    rc = _run(["--check", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0


def test_plural_agreement_n_greater_than_1(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, ["a", "b"])  # n = 2
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        _total_region("the panel of {n} {personas|persona}", "the panel of 2 personas")
    )
    rc = _run(["--check", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0


def test_subset_phrases_outside_regions_are_not_touched(tmp_path: Path) -> None:
    """A wrapped total phrase coexists with an unwrapped subset phrase.

    The generator must rewrite only the wrapped phrase; the surrounding
    text, including a numbered subset phrase like "1 persona objected"
    that legitimately names a subset, must be left byte-identical.
    """
    manifest = _write_manifest(tmp_path, ["a", "b", "c"])  # n = 3
    root = _make_corpus(tmp_path)
    f = root / "tests" / "scenarios" / "08.md"
    body = (
        "Pre-text: 1 persona objected, 2 personas approved.\n\n"
        + _total_region(
            "the panel of {n} {personas|persona}",
            "the panel of 99 personas",  # drifted
        )
        + "\nPost-text: 1 persona objected, 2 personas approved.\n"
    )
    f.write_text(body)
    rc = _run(["--write", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0
    out = f.read_text()
    assert out.count("1 persona objected") == 2
    assert out.count("2 personas approved") == 2
    assert "the panel of 3 personas" in out
    assert "the panel of 99 personas" not in out


def test_validate_markers_passes_on_balanced_tree(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, ["a", "b"])  # n = 2 (irrelevant for marker validation)
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        _total_region("{n} {personas|persona}", "2 personas")
        + _total_plus_1_region("{n} personas", "3 personas")
    )
    rc = _run(["--validate-markers", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0


def test_validate_markers_fails_on_unbalanced_start(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _write_manifest(tmp_path, ["a", "b"])
    root = _make_corpus(tmp_path)
    bad = root / "reviewers" / "broken.md"
    bad.write_text(
        "<!-- regen:panel-count-total:start -->\n"
        "<!-- template: the panel of {n} {personas|persona} -->\n"
        "the panel of 2 personas\n"
        # missing :end marker
    )
    rc = _run(["--validate-markers", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == regen_panel_counts._DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "broken.md" in err


def test_validate_markers_fails_on_orphan_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _write_manifest(tmp_path, ["a", "b"])
    root = _make_corpus(tmp_path)
    bad = root / "reviewers" / "orphan.md"
    bad.write_text("intro\n<!-- regen:panel-count-total:end -->\n")
    rc = _run(["--validate-markers", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == regen_panel_counts._DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "orphan.md" in err


def test_returns_3_when_manifest_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_corpus(tmp_path)
    missing = tmp_path / "no-such-personas.yaml"
    rc = _run(["--check", "--manifest", str(missing), "--corpus-root", str(root)])
    assert rc == regen_panel_counts._MANIFEST_ERROR_EXIT == 3
    err = capsys.readouterr().err
    assert "manifest error" in err


def test_zero_panel_renders_zero_personas_plural(tmp_path: Path) -> None:
    """the renderer supports zero even though manifests require a nonempty panel."""
    out = regen_panel_counts._render_template("the panel of {n} {personas|persona}", 0)
    assert out == "the panel of 0 personas"


def test_render_supports_markdown_formatting_around_n(tmp_path: Path) -> None:
    """Templates may include backticks or emphasis around `{n}`."""
    out = regen_panel_counts._render_template("the panel of `{n}` {personas|persona}", 7)
    assert out == "the panel of `7` personas"


def test_write_atomically_creates_no_tmp_files(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, ["a", "b"])  # n = 2
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(_total_region("{n} {personas|persona}", "99 personas"))
    rc = _run(["--write", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0
    leftover = list(root.rglob("*.tmp"))
    assert leftover == []


def test_validate_coverage_passes_on_empty_corpus(tmp_path: Path) -> None:
    """A corpus with no numbered persona-count phrases is trivially covered."""
    manifest = _write_manifest(tmp_path, ["a", "b"])
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text("intro paragraph\n\nno counts here\n")
    rc = _run(["--validate-coverage", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0


def test_validate_coverage_fails_on_unhandled_unwrapped_phrase(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unwrapped panel-count phrase that doesn't match the allowlist fails."""
    manifest = _write_manifest(tmp_path, ["a", "b"])
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text("the spec mentions 11 reviewer personas reviewing this PR\n")
    rc = _run(["--validate-coverage", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == regen_panel_counts._DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "unhandled numbered persona-count phrase" in err


def test_validate_coverage_allows_phrases_inside_regions(tmp_path: Path) -> None:
    """A panel-count phrase rendered inside a regen region is exempt.

    The rendered body is deliberately a phrase the allowlist would NOT
    match on its own (it's the same string that
    test_validate_coverage_fails_on_unhandled_unwrapped_phrase proves
    is closure-rejected when unwrapped). Wrapping it in a region must
    flip the verdict, isolating the region-exemption code path from
    the allowlist-exemption path.
    """
    manifest = _write_manifest(tmp_path, ["a", "b"])
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        _total_region(
            "the spec mentions {n} reviewer personas reviewing this PR",
            "the spec mentions 11 reviewer personas reviewing this PR",
        )
    )
    rc = _run(["--validate-coverage", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0


def test_validate_coverage_rejects_unwrapped_total_shaped_phrases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Total-shaped phrases outside regions must fail closure regardless of number.

    Authors are forced to wrap them so the manifest-driven --check pass
    verifies the number, instead of hand-allowlisting a shape that would
    silently accept any digit (the gap the deleted bats first/second
    @test blocks previously closed).
    """
    manifest = _write_manifest(tmp_path, ["a", "b"])
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        "the panel of 11 reviewer personas runs in parallel\n"
        "12 personas total (panel + adversary)\n"
        "the other 10 personas review\n"
    )
    rc = _run(["--validate-coverage", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == regen_panel_counts._DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "11 reviewer personas" in err
    assert "12 personas" in err
    assert "10 personas" in err


def test_validate_coverage_rejects_unwrapped_total_regardless_of_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both a matching and a wrong number fail outside a region.

    --validate-coverage doesn't compare digits against the manifest; it
    rejects unwrapped total shapes outright. Wrapping is the only way to
    pass, which then routes the numeric check to --check.
    """
    manifest = _write_manifest(tmp_path, ["a", "b"])  # len(panel) = 2

    # Wrong number (clearly drifted): must fail.
    wrong_root = _make_corpus(tmp_path / "wrong")
    (wrong_root / "SKILL.md").write_text("panel of 999 reviewer personas\n")
    rc = _run(
        ["--validate-coverage", "--manifest", str(manifest), "--corpus-root", str(wrong_root)]
    )
    assert rc == regen_panel_counts._DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "999 reviewer personas" in err

    # Matching number (still unwrapped): must also fail.
    match_root = _make_corpus(tmp_path / "match")
    (match_root / "SKILL.md").write_text("panel of 2 reviewer personas\n")
    rc = _run(
        ["--validate-coverage", "--manifest", str(manifest), "--corpus-root", str(match_root)]
    )
    assert rc == regen_panel_counts._DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "2 reviewer personas" in err


def test_validate_coverage_allows_subset_phrases(tmp_path: Path) -> None:
    """Subset-of-panel phrases (e.g. '2 personas approved') are allowlisted."""
    manifest = _write_manifest(tmp_path, ["a", "b"])
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        "after the round, 2 personas approved and 1 persona objected\n"
        "agreed by 3 personas\n"
        "4 Move C personas link to docs/procedure-moves.md\n"
    )
    rc = _run(["--validate-coverage", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0


def test_allowed_subset_does_not_hide_a_total_on_the_same_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text("The panel of 999 personas reviews; 2 personas approved.\n")
    rc = _run(["--validate-coverage", "--corpus-root", str(root)])
    assert rc == 5
    assert "999 personas" in capsys.readouterr().err


def test_validate_coverage_catches_phrase_split_across_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A numbered persona-count phrase wrapped across a line break still fails."""
    manifest = _write_manifest(tmp_path, ["a", "b"])
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text("the spec mentions 11\nreviewer personas reviewing this PR\n")
    rc = _run(["--validate-coverage", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == regen_panel_counts._DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "unhandled numbered persona-count phrase" in err


def test_validate_coverage_catches_parenthesized_phrase(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A persona-count phrase led by punctuation (no whitespace) still fails."""
    manifest = _write_manifest(tmp_path, ["a", "b"])
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text("(11 reviewer personas reviewing this PR)\n")
    rc = _run(["--validate-coverage", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == regen_panel_counts._DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "unhandled numbered persona-count phrase" in err


def test_validate_coverage_ignores_non_persona_numbers(tmp_path: Path) -> None:
    """Numbered tokens that aren't persona-counts (e.g. '5 minutes') are not flagged."""
    manifest = _write_manifest(tmp_path, ["a", "b"])
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        "wait 5 minutes for CI\n"
        "see issue #42 for context\n"
        "B2 persona is a Move A.1 sub-mechanic label\n"  # word-boundary anchor blocks this
    )
    rc = _run(["--validate-coverage", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0
