"""tests for generated panel-count phrases."""

from __future__ import annotations

from pathlib import Path

import generator_io
import pytest
import regen_panel_counts  # type: ignore[import-not-found]  # sibling module made importable by conftest.py
from personas_fixture import write_personas_yaml  # type: ignore[import-not-found]


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
    manifest = write_personas_yaml(tmp_path, ["a", "b", "c", "d", "e"])  # n = 5
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


@pytest.mark.parametrize("surface", ["SKILL.md", "reviewers/alpha.md", "tests/scenarios/01.md"])
def test_check_reports_drift_on_each_surface(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], surface: str
) -> None:
    manifest = write_personas_yaml(tmp_path, ["a", "b", "c"])  # n = 3
    root = _make_corpus(tmp_path)
    drifted = (
        "<!-- regen:panel-count-total:start -->\n"
        "<!-- template: the panel of {n} {personas|persona} -->\n"
        "the panel of 99 personas\n"  # drifted: should be 3
        "<!-- regen:panel-count-total:end -->\n"
    )
    (root / surface).write_bytes(drifted.rstrip("\n").replace("\n", "\r").encode())
    rc = _run(["--check", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == generator_io.DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert f"--- {root / surface}\n" in err
    assert "regen.sh" in err
    lines = err.split("\n")
    assert "-the panel of 99 personas" in lines
    assert "+the panel of 3 personas" in lines
    end = lines.index(" <!-- regen:panel-count-total:end -->")
    assert lines[end + 1] == r"\ No newline at end of file"


def test_write_repairs_drift_across_all_surfaces(tmp_path: Path) -> None:
    manifest = write_personas_yaml(tmp_path, ["a", "b", "c", "d"])  # n = 4
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
    assert skill.read_text() == _total_region(
        "panel of {n} reviewer {personas|persona}", "panel of 4 reviewer personas"
    )
    assert scen.read_text() == _total_plus_1_region(
        "{n} personas total (panel + adversary)", "5 personas total (panel + adversary)"
    )
    assert rev.read_text() == _total_region(
        "the other {n} {personas|persona}", "the other 4 personas"
    )
    rc = _run(["--check", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0


def test_plural_agreement_n_equals_1(tmp_path: Path) -> None:
    manifest = write_personas_yaml(tmp_path, ["solo"])  # n = 1
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        _total_region("the panel of {n} {personas|persona}", "the panel of 1 persona")
    )
    rc = _run(["--check", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0


def test_plural_agreement_n_greater_than_1(tmp_path: Path) -> None:
    manifest = write_personas_yaml(tmp_path, ["a", "b"])  # n = 2
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        _total_region("the panel of {n} {personas|persona}", "the panel of 2 personas")
    )
    rc = _run(["--check", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0


@pytest.mark.parametrize(
    ("body_ending", "ending"),
    [("\n", "\n"), ("\r\n", "\r\n"), ("\r", "\r"), ("\n", "\r\n")],
    ids=["lf", "crlf", "cr", "mixed"],
)
def test_subset_phrases_outside_regions_are_not_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body_ending: str, ending: str
) -> None:
    """A wrapped total phrase coexists with an unwrapped subset phrase.

    The generator must rewrite only the wrapped phrase; the surrounding
    text, including a numbered subset phrase like "1 persona objected"
    that legitimately names a subset, must be left byte-identical.
    """
    manifest = write_personas_yaml(tmp_path, ["a", "b", "c"])  # n = 3
    with manifest.open("a", encoding="utf-8") as stream:
        stream.write("# UTF-8 fixture: ā\n")
    root = _make_corpus(tmp_path)
    f = root / "tests" / "scenarios" / "08.md"
    body = (
        "ā: 1 persona objected,\u20282 personas approved.\n\n"
        + _total_region(
            "the panel of {n} {personas|persona}",
            "the panel of 99 personas",  # drifted
        )
        + "\nPost-text: 1 persona objected, 2 personas approved.\n"
    )
    original = (
        body.replace("\n", ending)
        .replace("99 personas" + ending, "99 personas" + body_ending)
        .encode()
    )
    f.write_bytes(original)

    # model Windows defaults for Path.open. UTF-8 ā contains a byte undefined in cp1252.
    open_path = Path.open

    def open_with_windows_defaults(
        path: Path, mode="r", buffering=-1, encoding=None, errors=None, newline=None
    ):
        if "b" not in mode:
            if encoding in (None, "locale"):
                encoding = "cp1252"
            if "w" in mode and newline is None:
                newline = "\r\n"
        return open_path(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", open_with_windows_defaults)
    rc = _run(["--write", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0
    assert f.read_bytes() == original.replace(
        b"the panel of 99 personas", b"the panel of 3 personas"
    )
    assert _run(["--check", "--manifest", str(manifest), "--corpus-root", str(root)]) == 0


@pytest.mark.parametrize("final_lf", ["", "\n"], ids=["eof", "lf"])
@pytest.mark.parametrize(
    "mode", ["--check", "--write", "--validate-markers", "--validate-coverage"]
)
def test_closing_marker_accepts_trailing_unicode_whitespace(
    tmp_path: Path, final_lf: str, mode: str
) -> None:
    root = _make_corpus(tmp_path)
    target = root / "SKILL.md"
    original = (
        _total_region("{n} personas", "2 personas").rstrip("\n") + "\u2028" + final_lf
    ).encode()
    target.write_bytes(original)
    args = [mode, "--corpus-root", str(root)]
    if mode in ("--check", "--write"):
        args.extend(["--manifest", str(write_personas_yaml(tmp_path, ["a", "b"]))])
    assert _run(args) == 0
    assert target.read_bytes() == original


@pytest.mark.parametrize(
    "mode", ["--check", "--write", "--validate-markers", "--validate-coverage"]
)
@pytest.mark.parametrize("indent", ["", " "])
def test_unicode_separator_in_prose_does_not_start_a_marker_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], mode: str, indent: str
) -> None:
    root = _make_corpus(tmp_path)
    path = root / "SKILL.md"
    original = f"prose\u2028{indent}<!-- regen:panel-count-total:end -->\n"
    path.write_text(original)
    args = [mode, "--corpus-root", str(root)]
    if mode in ("--check", "--write"):
        args.extend(["--manifest", str(write_personas_yaml(tmp_path, ["a", "b"]))])
    assert _run(args) == generator_io.DRIFT_EXIT
    assert "line 1: put the marker on its own physical line" in capsys.readouterr().err
    assert path.read_text() == original


@pytest.mark.parametrize(
    ("template", "body", "error_line"),
    [
        ("{n} personas", "<!-- regen:panel-count-total:start -->", 3),
        ("{n} personas", "    <!-- regen:panel-count-total:end -->", 3),
        ("{n} personas", "2 personas\u2028<!-- regen:panel-count-total:start -->", 3),
        ("{n} personas", "2 personas <!-- regen:panel-count-total:end -->", 3),
        ("{n} personas", "<!-- template: extra -->", 3),
        ("<!-- regen:panel-count-total:start -->", "ordinary prose", 2),
        ("<!-- regen:panel-count-total-plus-{n}:start -->", "ordinary prose", 2),
        ("<!-- template: inner -->", "ordinary prose", 2),
        ("<!-- template: inner", "ordinary prose", 2),
        ("{n} personas", "<!-- template:  -->", 3),
    ],
)
def test_write_preserves_a_region_containing_another_marker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], template: str, body: str, error_line: int
) -> None:
    root = _make_corpus(tmp_path)
    path = root / "SKILL.md"
    original = _total_region(template, body).encode()
    path.write_bytes(original)
    manifest = write_personas_yaml(tmp_path, ["one"])
    assert _run(["--write", "--corpus-root", str(root), "--manifest", str(manifest)]) == 5
    assert f"line {error_line}:" in capsys.readouterr().err
    assert path.read_bytes() == original


def test_write_rejects_a_start_marker_in_the_closing_slot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_corpus(tmp_path)
    path = root / "SKILL.md"
    original = (
        _total_region("{n} personas", "99 personas").replace(":end -->", ":start -->").encode()
    )
    path.write_bytes(original)
    manifest = write_personas_yaml(tmp_path, ["one"])
    assert _run(["--write", "--corpus-root", str(root), "--manifest", str(manifest)]) == 5
    assert "line 4: expected regen:panel-count-total:end" in capsys.readouterr().err
    assert path.read_bytes() == original


def test_validate_markers_passes_on_balanced_tree(tmp_path: Path) -> None:
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        "Inline example: `<!-- regen:panel-count-total:start -->`.\n"
        + _total_region("{n} {personas|persona}", "2 personas")
        + _total_plus_1_region("{n} personas", "3 personas")
    )
    rc = _run(["--validate-markers", "--corpus-root", str(root)])
    assert rc == 0


def test_validate_markers_fails_on_unbalanced_start(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_corpus(tmp_path)
    bad = root / "reviewers" / "broken.md"
    bad.write_text(
        "<!-- regen:panel-count-total:start -->\n"
        "<!-- template: the panel of {n} {personas|persona} -->\n"
        "the panel of 2 personas\n"
        # missing :end marker
    )
    rc = _run(["--validate-markers", "--corpus-root", str(root)])
    assert rc == generator_io.DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "broken.md" in err


def test_validate_markers_fails_on_orphan_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_corpus(tmp_path)
    bad = root / "reviewers" / "orphan.md"
    bad.write_text("intro\n<!-- regen:panel-count-total:end -->\n")
    rc = _run(["--validate-markers", "--corpus-root", str(root)])
    assert rc == generator_io.DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "orphan.md" in err


def test_returns_3_when_manifest_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_corpus(tmp_path)
    missing = tmp_path / "no-such-personas.yaml"
    rc = _run(["--check", "--manifest", str(missing), "--corpus-root", str(root)])
    assert rc == generator_io.MANIFEST_ERROR_EXIT == 3
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


def test_write_replaces_target_and_leaves_no_tmp_files(tmp_path: Path) -> None:
    manifest = write_personas_yaml(tmp_path, ["a", "b"])  # n = 2
    root = _make_corpus(tmp_path)
    target = root / "SKILL.md"
    target.write_text(_total_region("{n} {personas|persona}", "99 personas"))
    original_inode = target.stat().st_ino
    rc = _run(["--write", "--manifest", str(manifest), "--corpus-root", str(root)])
    assert rc == 0
    assert target.read_text() == _total_region("{n} {personas|persona}", "2 personas")
    assert target.stat().st_ino != original_inode
    leftover = list(root.rglob("*.tmp"))
    assert leftover == []


def test_validate_coverage_passes_without_count_phrases(tmp_path: Path) -> None:
    """A corpus with no numbered persona-count phrases is trivially covered."""
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text("intro paragraph\n\nno counts here\n")
    rc = _run(["--validate-coverage", "--corpus-root", str(root)])
    assert rc == 0


def test_validate_coverage_fails_on_unhandled_unwrapped_phrase(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unwrapped panel-count phrase that doesn't match the allowlist fails."""
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text("the spec mentions 11 reviewer personas reviewing this PR\n")
    rc = _run(["--validate-coverage", "--corpus-root", str(root)])
    assert rc == generator_io.DRIFT_EXIT == 5
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
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        _total_region(
            "the spec mentions {n} reviewer personas reviewing this PR",
            "the spec mentions 11 reviewer personas reviewing this PR",
        )
    )
    rc = _run(["--validate-coverage", "--corpus-root", str(root)])
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
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        "the panel of 11 reviewer personas runs in parallel\n"
        "12 personas total (panel + adversary)\n"
        "the other 10 personas review\n"
    )
    rc = _run(["--validate-coverage", "--corpus-root", str(root)])
    assert rc == generator_io.DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "11 reviewer personas" in err
    assert "12 personas" in err
    assert "10 personas" in err


def test_validate_coverage_rejects_unwrapped_total_regardless_of_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = write_personas_yaml(tmp_path, ["a", "b"])
    wrong_root = _make_corpus(tmp_path / "wrong")
    (wrong_root / "SKILL.md").write_text("panel of 999 reviewer personas\n")
    rc = _run(
        ["--validate-coverage", "--manifest", str(manifest), "--corpus-root", str(wrong_root)]
    )
    assert rc == generator_io.DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "999 reviewer personas" in err

    match_root = _make_corpus(tmp_path / "match")
    (match_root / "SKILL.md").write_text("panel of 2 reviewer personas\n")
    rc = _run(
        ["--validate-coverage", "--manifest", str(manifest), "--corpus-root", str(match_root)]
    )
    assert rc == generator_io.DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "2 reviewer personas" in err


def test_validate_coverage_allows_subset_phrases(tmp_path: Path) -> None:
    """Subset-of-panel phrases (e.g. '2 personas approved') are allowlisted."""
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        "after the round, 2 personas approved and 1 persona objected\n"
        "agreed by 3 personas\n"
        "Of the five selected, three abstained and the other 2 personas approved.\n"
        "Five were selected and all of the 5 personas approved.\n"
        "Enter the amount the invoices agreed by 3 personas total.\n"
        "Find what the invoices agreed by 3 personas total, including tax.\n"
        "We checked (how much the invoices agreed by 3 personas total) before paying.\n"
        "What do the invoices agreed by 3 personas total?\n"
        "3 personas agreed in total\n"
        "The proposal was agreed by 3 personas in total silence.\n"
        "The proposal was agreed by 3 personas in total  \nsilence.\n"
        "The proposal was agreed by 3 personas in **total**\nsilence.\n"
        "The revisions agreed by 3 personas total, on average, five pages.\n"
        "The reports agreed by 3 personas total, excluding appendices, five pages.\n"
        "The decision was agreed by 3 personas in total across-the-board silence.\n"
        "The report was agreed by 3 personas in total, stunned silence.\n"
        "The revisions agreed by 3 personas total five pages.\n"
        "The revisions agreed by 3 personas total (on average) five pages.\n"
        "4 Move C personas link to docs/procedure-moves.md\n"
    )
    rc = _run(["--validate-coverage", "--corpus-root", str(root)])
    assert rc == 0


@pytest.mark.parametrize(
    ("phrase", "total"),
    [
        ("The panel of 999 personas agreed", "panel of 999 personas"),
        ("A total of 11 personas agreed", "A total of 11 personas"),
        ("A total of **11 personas agreed**", "A total of **11 personas"),
        ("A total of **11 personas agreed.**", "A total of **11 personas"),
        ("A total of **`11` personas agreed**.", "A total of **`11` personas"),
        ("agreed by 12 personas **total (Panel + Adversary)**.", "12 personas **total"),
        ("A total of _11_ personas agreed", "A total of _11_ personas"),
        ("A total of **11** personas agreed", "A total of **11** personas"),
        ("A total of `11` personas agreed", "A total of `11` personas"),
        ("agreed by 12 personas **in total**", "12 personas **in total**"),
        ("A total of **11 personas** agreed", "A total of **11 personas**"),
        ("*A total of **`11` personas agreed***.", "A total of **`11` personas"),
        ("A total of ***`11`** personas* agreed.", "A total of ***`11`** personas"),
        ("Total: 11 personas agreed", "Total: 11 personas"),
        ("> A total of\n11 personas agreed", "A total of\n11 personas"),
        ("> 11\npersonas reviewed the changes.", "11\npersonas"),
        ("agreed by 12 personas, in total across two rounds", "12 personas, in total"),
        ("agreed by 12 personas, in total, after two rounds.", "12 personas, in total"),
        ("agreed by 12 personas, in total.", "12 personas, in total"),
        ("> A total of\n> 11 personas agreed", "A total of\n> 11 personas"),
        ("agreed by 12 personas in total, across two rounds", "12 personas in total"),
        ("In total 11 personas agreed", "In total 11 personas"),
        ("In total, 11 personas agreed", "In total, 11 personas"),
        ("agreed by 12 personas in total across two rounds", "12 personas in total"),
        ("agreed by 3 personas\nTotal of 11 personas agreed", "Total of 11 personas"),
        ("agreed by 12 personas total (Panel + Adversary)", "12 personas total"),
        ("Agreed by 3 personas in total (Panel + Adversary)", "3 personas in total"),
        ("agreed by 12 personas in total", "12 personas in total"),
        (
            "agreed by 12 personas, in total, excluding Alex, Blair, and Casey.",
            "12 personas, in total",
        ),
        ("agreed by 12 personas in total, including two new members", "12 personas in total"),
    ],
)
def test_allowed_subset_does_not_hide_an_explicit_total(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], phrase: str, total: str
) -> None:
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(f"{phrase}; 2 personas approved.\n")
    assert _run(["--validate-coverage", "--corpus-root", str(root)]) == 5
    err = capsys.readouterr().err
    label = "unhandled numbered persona-count phrase: "
    assert [line.partition(label)[2] for line in err.splitlines() if label in line] == [repr(total)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "agreed by 3 personas in total\nA total of 11 personas agreed",
            ["3 personas in total", "A total of 11 personas"],
        ),
        (
            "A total of 3 personas  \nIn total, 11 personas agreed",
            ["A total of 3 personas", "In total, 11 personas"],
        ),
        ("Agreed by 3 personas in total  \n12 personas approved.", ["3 personas in total"]),
        ("Agreed by 3 personas  \nIn total, 11 personas agreed", ["In total, 11 personas"]),
    ],
)
def test_adjacent_counts_keep_their_own_qualifiers(tmp_path: Path, capsys, text, expected) -> None:
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(text)
    assert _run(["--validate-coverage", "--corpus-root", str(root)]) == 5
    reports = [
        line.partition("unhandled numbered persona-count phrase: ")[2]
        for line in capsys.readouterr().err.splitlines()
        if "unhandled numbered persona-count phrase: " in line
    ]
    assert reports == [repr(phrase) for phrase in expected]


def test_headings_and_blank_lines_separate_total_qualifiers_from_allowed_subsets(
    tmp_path: Path,
) -> None:
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        "## A total of\n \n2 personas approved.\n\nagreed by 3 personas\n\nTotal elapsed time.\n"
        "A total of\n\n11 personas agreed.\n"
        "## A total of\n2 personas approved.\n"
        "> ## A total of\n3 personas agreed.\n"
        "> A total of\n>> 2 personas approved.\n"
        "> A total of\n>\n> 3 personas agreed.\n"
    )
    assert _run(["--validate-coverage", "--corpus-root", str(root)]) == 0


@pytest.mark.parametrize("container", ["- ", "1. ", "> - "])
def test_list_headings_keep_their_own_counts(tmp_path: Path, capsys, container: str) -> None:
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        f"{container}## 99 personas: A total of\n  2 personas approved.\n"
    )
    assert _run(["--validate-coverage", "--corpus-root", str(root)]) == 5
    label = "unhandled numbered persona-count phrase: "
    assert [
        line.partition(label)[2] for line in capsys.readouterr().err.splitlines() if label in line
    ] == ["'99 personas'"]


def test_validate_coverage_catches_phrase_split_across_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A numbered persona-count phrase wrapped across a line break still fails."""
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_bytes(
        b"intro\r\n\r\nthe spec mentions 11\r\nreviewer personas reviewing this PR\r\n"
    )
    rc = _run(["--validate-coverage", "--corpus-root", str(root)])
    assert rc == generator_io.DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "line 3: unhandled numbered persona-count phrase" in err


def test_validate_coverage_catches_parenthesized_phrase(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A persona-count phrase led by punctuation (no whitespace) still fails."""
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text("(11 reviewer personas reviewing this PR)\n")
    rc = _run(["--validate-coverage", "--corpus-root", str(root)])
    assert rc == generator_io.DRIFT_EXIT == 5
    err = capsys.readouterr().err
    assert "unhandled numbered persona-count phrase" in err


def test_validate_coverage_ignores_non_persona_numbers(tmp_path: Path) -> None:
    """Numbered tokens that aren't persona-counts (e.g. '5 minutes') are not flagged."""
    root = _make_corpus(tmp_path)
    (root / "SKILL.md").write_text(
        "wait 5 minutes for CI\n"
        "see issue #42 for context\n"
        "The labels are \\_11 personas and status_.\n"
        "An escaped backtick precedes a span: \\``_11 personas_`.\n"
        "The code spans are `_11 personas` and `status_`.\n"
        "The review log uses the label _11 personas for the next stage.\n"
        "B2 persona is a Move A.1 sub-mechanic label\n"  # word-boundary anchor blocks this
    )
    rc = _run(["--validate-coverage", "--corpus-root", str(root)])
    assert rc == 0
