"""Tests for report.py: fixture-driven rendering."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
from _shared import finding_id
from collect_pr_corpus import (  # type: ignore[import-not-found]  # noqa: E402 : sibling module made importable by conftest.py
    CORPUS_VERSION,
    corpus_filename,
    matched_filename,
)
from report import (
    _candidate_cause,  # type: ignore[import-not-found]  # noqa: E402 : sibling module made importable by conftest.py
)

HARNESS = Path(__file__).resolve().parents[1]
SCRIPT = HARNESS / "report.py"


DEFAULT_OWNER = "o"
DEFAULT_REPO = "r"


def _write_jsonl(path: Path, rows):
    """Write matcher-output JSONL, stamping the scorer A2 records on every row.

    Defaulted rather than required so test bodies stay about bucket semantics; a
    test that cares about the scorer guard passes `scorer` explicitly and this
    leaves it alone.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    stamped = [{"scorer": "token_containment@0.5/win15", **r} for r in rows]
    path.write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in stamped) + ("\n" if stamped else "")
    )


def _write_labels(path: Path, rows):
    """Write labels.csv. Each row is (pr, bucket, finding_id, label, notes); the
    owner/repo columns are prepended automatically using DEFAULT_OWNER/REPO so
    test bodies stay focused on the bucket/label semantics."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["owner", "repo", "pr", "bucket", "finding_id", "label", "notes"])
        for r in rows:
            w.writerow([DEFAULT_OWNER, DEFAULT_REPO, *r])


def _corpus_path(tmp_path: Path, pr: int) -> Path:
    """Path used both for writing fixtures and pointing report.py at the
    fixture root. Creates the nested owner/repo parents so test bodies can
    `.write_text(...)` directly without an extra mkdir step."""
    path = tmp_path / "corpus" / corpus_filename(DEFAULT_OWNER, DEFAULT_REPO, pr)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _jsonl_path(tmp_path: Path, bucket: str, pr: int) -> Path:
    return tmp_path / bucket / matched_filename(DEFAULT_OWNER, DEFAULT_REPO, pr)


def _corpus_record(pr: int, **overrides) -> dict:
    base = {
        "corpus_version": CORPUS_VERSION,
        "pr": pr,
        "owner": DEFAULT_OWNER,
        "repo": DEFAULT_REPO,
        "loop_findings": [],
        "loop_findings_unanchored": [],
        "external_findings": [],
    }
    base.update(overrides)
    return base


def _run(tmp_path, sample_rate=1.0, sample_min=1):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--unmatched-dir",
            str(tmp_path / "unmatched"),
            "--matched-dir",
            str(tmp_path / "matched"),
            "--loop-unmatched-dir",
            str(tmp_path / "loop_unmatched"),
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--labels",
            str(tmp_path / "labels.csv"),
            "--sample-rate",
            str(sample_rate),
            "--sample-min",
            str(sample_min),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _render_with_unmatched_records(tmp_path, unmatched, labels_rows=None) -> str:
    """Build a minimal one-PR corpus + the supplied unmatched JSONL + an
    empty matched JSONL, then invoke report.py and return its stdout.

    Centralizes the fixture so all near-miss section tests share
    the same corpus shape and labels.csv schema. The corpus is hard-coded
    to `(owner=DEFAULT_OWNER, repo=DEFAULT_REPO, pr=1)`; `labels_rows`
    must use the same `pr=1` and is prepended with the same owner/repo
    via `_write_labels` so the lookup at report.py joins correctly.
    Each labels_rows entry is the same 5-tuple shape `_write_labels`
    already accepts: `(pr, bucket, finding_id, label, notes)`. Passing
    a mismatched owner/repo/pr is structurally impossible: that was
    the original fixture-mismatch bug this helper exists to prevent.

    `external_findings` is populated to mirror the unmatched JSONL
    one-for-one so the invariant at report.py
    (`len(matched) + len(unmatched) == anchored_externals`) holds; without
    this, every test run pollutes stdout with a `## PIPELINE WARNING —
    stale matcher outputs` section, and a future test asserting that
    warning is absent from a clean fixture would false-fail. The mirrored
    externals carry the same file/line as the unmatched record so
    `_is_anchored` (match_external.py) counts them."""
    (tmp_path / "corpus").mkdir(exist_ok=True)
    mirrored_externals = [
        {
            "file": u["external"]["file"],
            "line": u["external"]["line"],
            "summary": u["external"].get("summary", ""),
        }
        for u in unmatched
    ]
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(_corpus_record(1, external_findings=mirrored_externals))
    )
    _write_jsonl(_jsonl_path(tmp_path, "unmatched", 1), unmatched)
    _write_jsonl(_jsonl_path(tmp_path, "matched", 1), [])
    _write_labels(tmp_path / "labels.csv", labels_rows or [])
    return _run(tmp_path)


def test_report_renders_with_no_data(tmp_path):
    """Empty inputs produce an empty-but-valid report."""
    (tmp_path / "corpus").mkdir()
    (tmp_path / "labels.csv").write_text("owner,repo,pr,bucket,finding_id,label,notes\n")
    out = _run(tmp_path)
    assert "# Recall harness report" in out
    assert "PRs analyzed: 0" in out


def test_report_totals_and_grouping(tmp_path):
    (tmp_path / "corpus").mkdir()
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                loop_findings=[{"file": "a", "line": 1, "summary": "x"}],
                external_findings=[
                    {"file": "a", "line": 1, "summary": "ok", "source": "copilot"},
                    {"file": "a", "line": 1, "summary": "miss", "source": "copilot"},
                ],
            )
        )
    )
    _write_jsonl(
        _jsonl_path(tmp_path, "unmatched", 1),
        [
            {
                "finding_id": "aaa111",
                "external": {
                    "file": "a",
                    "line": 1,
                    "summary": "missing timeout on fetch",
                    "source": "copilot",
                },
            },
        ],
    )
    _write_jsonl(
        _jsonl_path(tmp_path, "matched", 1),
        [
            {
                "finding_id": "bbb222",
                "external": {"file": "a", "line": 1, "summary": "ok"},
                "matched_loop": {"file": "a", "line": 1, "summary": "x"},
            },
        ],
    )
    _write_labels(
        tmp_path / "labels.csv",
        [
            ["1", "unmatched", "aaa111", "real_miss", ""],
            ["1", "matched_sample", "bbb222", "matched_true", ""],
        ],
    )

    out = _run(tmp_path)
    assert "PRs analyzed: 1" in out
    assert "real_miss" in out
    assert "matched_false rate" in out
    assert "config / env coupling" in out  # keyword-grouped real_miss appears
    assert "By owner/repo" in out  # per-repo section is present


def test_report_flags_high_matched_false_rate(tmp_path):
    (tmp_path / "corpus").mkdir()
    _corpus_path(tmp_path, 1).write_text(json.dumps(_corpus_record(1)))
    _write_jsonl(
        _jsonl_path(tmp_path, "matched", 1),
        [
            {
                "finding_id": f"id{i:03d}",
                "external": {"file": "a", "line": 1, "summary": "s"},
                "matched_loop": {},
            }
            for i in range(10)
        ],
    )
    _write_jsonl(_jsonl_path(tmp_path, "unmatched", 1), [])
    rows = []
    for i in range(10):
        label = "matched_false" if i < 8 else "matched_true"
        rows.append(["1", "matched_sample", f"id{i:03d}", label, ""])
    _write_labels(tmp_path / "labels.csv", rows)

    out = _run(tmp_path)
    assert "MATCHER QUALITY WARNING" in out


@pytest.mark.parametrize(
    ("label", "judged", "rate", "warning"),
    [
        (None, 0, "n/a", False),
        ("matched_false", 1, "100.0%", True),
        ("matched_true", 1, "0.0%", False),
    ],
)
def test_matcher_quality_counts_only_judged_sampled_pairs(tmp_path, label, judged, rate, warning):
    loops = [{"file": f"f{i}.py", "line": i + 1, "summary": f"issue {i}"} for i in range(11)]
    externals = [{**finding, "source": "copilot"} for finding in loops]
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(_corpus_record(1, loop_findings=loops, external_findings=externals))
    )
    _write_jsonl(
        _jsonl_path(tmp_path, "matched", 1),
        [
            {"finding_id": f"id{i:03d}", "external": external, "matched_loop": loop}
            for i, (external, loop) in enumerate(zip(externals, loops, strict=True))
        ],
    )
    _write_jsonl(_jsonl_path(tmp_path, "unmatched", 1), [])
    _write_loop_unmatched(tmp_path, 1, [])
    _write_labels(
        tmp_path / "labels.csv", [(1, "matched_sample", "id000", label, "")] if label else []
    )
    out = _run(tmp_path)
    assert f"Judged sampled pairs: {judged}/11" in out
    assert f"matched_false rate: {rate}" in out
    assert ("MATCHER QUALITY WARNING" in out) is warning
    assert "PIPELINE WARNING" not in out


def test_matched_false_rate_renders_na_on_empty_sample(tmp_path):
    """`0.0%` off a zero denominator reads as a measured pass. With no matched
    pairs the rate is not computable, and the report has to say so."""
    (tmp_path / "corpus").mkdir()
    _corpus_path(tmp_path, 1).write_text(json.dumps(_corpus_record(1)))
    _write_jsonl(_jsonl_path(tmp_path, "matched", 1), [])
    _write_jsonl(_jsonl_path(tmp_path, "unmatched", 1), [])
    _write_labels(tmp_path / "labels.csv", [])

    out = _run(tmp_path)
    assert "matched_false rate: n/a" in out
    assert "matched_false rate: 0.0%" not in out


def test_matcher_quality_warning_suppressed_on_empty_sample(tmp_path):
    (tmp_path / "corpus").mkdir()
    _corpus_path(tmp_path, 1).write_text(json.dumps(_corpus_record(1)))
    _write_jsonl(_jsonl_path(tmp_path, "matched", 1), [])
    _write_jsonl(_jsonl_path(tmp_path, "unmatched", 1), [])
    _write_labels(tmp_path / "labels.csv", [])

    assert "MATCHER QUALITY WARNING" not in _run(tmp_path)


def test_candidate_cause_groups_test_coverage_summaries():
    assert "test coverage" in _candidate_cause("test setup did not cover null path")
    assert "test coverage" in _candidate_cause("assertion does not exercise behavior")


def test_candidate_cause_does_not_misclassify_substring_matches():
    """Substring matching put 'latest' under 'test coverage'; tokenization
    must not. Word-boundary matching is the load-bearing guarantee here."""
    assert "test coverage" not in _candidate_cause("the latest release broke this path")
    assert "test coverage" not in _candidate_cause("contest results show parser drift")
    # 'fail' must not match 'failure mode' grouping when embedded in a word.
    assert "error-path coverage" not in _candidate_cause("the resolved path was unaffected")


def test_candidate_cause_handles_multiword_keywords():
    """Multi-word keys like 'shared state', 'env var', 'feature flag' still
    classify even though they aren't single tokens."""
    assert "concurrency / ordering" in _candidate_cause("shared state read without lock")
    assert "config / env coupling" in _candidate_cause("missing env var fallback")
    assert "config / env coupling" in _candidate_cause("feature flag default changed silently")


def test_candidate_cause_falls_back_when_no_keywords_hit():
    cause = _candidate_cause("readable variable names would help")
    assert cause == "unrecoverable or uncategorized"


def test_candidate_cause_groups_schema_constraint_summaries_without_schema_token():
    """Schema-constraint summaries that describe a 'required list' or
    'additional properties' without using 'schema'/'type' must still route
    to type_design: these are the documented-but-unenforced patterns the
    type_design persona sharpens for."""
    summary = (
        "The new object form for history[].addressed[]/deferred[] doesn't require "
        "any fields and allows arbitrary additional properties. Consider adding a "
        "required list and tightening additionalProperties."
    )
    assert "type design" in _candidate_cause(summary)
    # Each multi-word vocabulary item should classify on its own, so a future
    # type_design-shaped finding using only one of these phrases still routes
    # correctly.
    assert "type design" in _candidate_cause("the spec documents a required list")
    assert "type design" in _candidate_cause("additionalProperties is wide open")
    assert "type design" in _candidate_cause("mutually exclusive flags both representable")
    assert "type design" in _candidate_cause("schema does not validate the cap")
    # 'invariant' is the only other single-word key in the type_design tuple
    # (besides 'schema'): labels.csv carries 'missing invariant check' as a
    # real_miss note, so this routing is load-bearing.
    assert "type design" in _candidate_cause("missing invariant check on the response")
    # A representative sample of the new multi-word keys, so a future narrowing
    # has at least one assertion per vocabulary family to catch regressions.
    assert "type design" in _candidate_cause("the type signature does not constrain N")
    assert "type design" in _candidate_cause("enforce schema constraint at boundary")


def test_candidate_cause_routes_type_design_before_error_path():
    """A summary like 'schema fails to validate' contains both a type_design
    signal ('schema') and an error-path signal ('fail'). The branch ordering
    must put type_design first, otherwise documented-but-unenforced findings
    that happen to include failure vocabulary would land in error-path
    coverage instead."""
    assert "type design" in _candidate_cause("schema fails to validate the required list")
    assert "type design" in _candidate_cause("raises when the required field is missing")
    assert "type design" in _candidate_cause("validator throws on additional properties")


def test_candidate_cause_does_not_steal_from_other_buckets():
    """The type_design reorder must not steal findings whose vocabulary
    incidentally overlaps with type_design's broad words. Bare 'type' and
    'enforce' are restricted to multi-word phrases for exactly this reason —
    these negative assertions pin that constraint so a future broadening
    can't silently regress other buckets."""
    # 'type' as plain English must not pull the finding into type_design.
    assert "type design" not in _candidate_cause("non-mapping type passed to safe_load")
    assert "type design" not in _candidate_cause("the type was tested in isolation")
    # 'interface' as in API surface (security/auth context) must not match.
    assert "type design" not in _candidate_cause("auth interface needs review for csrf")
    assert "security" in _candidate_cause("auth interface needs review for csrf")
    # 'enforce' as in policy/limits (config/env context) must not match.
    assert "type design" not in _candidate_cause("enforce rate limit fallback in config")
    assert "config" in _candidate_cause("enforce rate limit fallback in config")
    # A pure error-path summary with no type_design signal stays in error-path.
    assert "type design" not in _candidate_cause("the resolver raises an exception on bad input")
    assert "error-path" in _candidate_cause("the resolver raises an exception on bad input")
    # A pure tests summary with no type_design signal stays in tests.
    assert "type design" not in _candidate_cause("assertion does not cover the null branch")
    assert "test coverage" in _candidate_cause("assertion does not cover the null branch")
    # The reorder put type_design AFTER config/env + concurrency, so a summary
    # mixing a type_design token with a concurrency/config signal must land
    # in the earlier bucket. ('config' wins over 'concurrency' here only
    # because of tuple ordering: both are upstream of type_design, which
    # is the invariant being pinned.)
    assert "type design" not in _candidate_cause("schema race on async config reload")
    assert "type design" not in _candidate_cause("schema race condition in async handler")
    assert "concurrency" in _candidate_cause("schema race condition in async handler")


def test_report_warns_when_matched_unmatched_mismatch_anchored(tmp_path):
    """If A1 regenerated the corpus but A2 didn't rerun, the bucket totals
    are stale relative to the corpus: report.py must surface that loudly
    rather than letting downstream sections silently mislead the reader."""
    (tmp_path / "corpus").mkdir()
    # Corpus says 3 anchored externals.
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                external_findings=[
                    {"file": "a", "line": 1, "summary": "x", "source": "copilot"},
                    {"file": "a", "line": 2, "summary": "y", "source": "copilot"},
                    {"file": "a", "line": 3, "summary": "z", "source": "copilot"},
                ],
            )
        )
    )
    # But matched/ + unmatched/ describe only 2 (stale).
    _write_jsonl(
        _jsonl_path(tmp_path, "unmatched", 1),
        [{"finding_id": "id1", "external": {"file": "a", "line": 1, "summary": "x"}}],
    )
    _write_jsonl(
        _jsonl_path(tmp_path, "matched", 1),
        [
            {
                "finding_id": "id2",
                "external": {"file": "a", "line": 2, "summary": "y"},
                "matched_loop": {},
            }
        ],
    )
    _write_labels(tmp_path / "labels.csv", [])

    out = _run(tmp_path)
    assert "PIPELINE WARNING" in out
    assert f"{DEFAULT_OWNER}/{DEFAULT_REPO} PR #1: anchored_external=3" in out
    assert "matched+unmatched=2" in out
    # The warning must precede `## Totals` so a reader skimming the top can't
    # trust the matched/unmatched numbers without seeing the staleness disclaimer.
    assert out.index("PIPELINE WARNING") < out.index("## Totals"), (
        "PIPELINE WARNING must be emitted above Totals so its disclaimer is "
        "visible before the (potentially stale) matched/unmatched counts."
    )


def test_report_no_pipeline_warning_when_buckets_consistent(tmp_path):
    """No warning when matched + unmatched == anchored_external."""
    (tmp_path / "corpus").mkdir()
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                external_findings=[
                    {"file": "a", "line": 1, "summary": "x", "source": "copilot"},
                ],
            )
        )
    )
    _write_jsonl(
        _jsonl_path(tmp_path, "unmatched", 1),
        [{"finding_id": "id1", "external": {"file": "a", "line": 1, "summary": "x"}}],
    )
    _write_jsonl(_jsonl_path(tmp_path, "matched", 1), [])
    _write_labels(tmp_path / "labels.csv", [])

    out = _run(tmp_path)
    assert "PIPELINE WARNING" not in out


def test_report_includes_unanchored_bucket_labels_in_distribution(tmp_path):
    """label.md defines unanchored_external + unanchored_loop buckets; report
    must tally any labels.csv rows in those buckets so the documented buckets
    aren't silently ignored."""
    (tmp_path / "corpus").mkdir()
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                loop_findings_unanchored=[{"summary": "ci item"}],
                external_findings=[
                    {"file": None, "line": None, "summary": "overall LGTM", "source": "copilot"},
                ],
            )
        )
    )
    _write_jsonl(_jsonl_path(tmp_path, "unmatched", 1), [])
    _write_jsonl(_jsonl_path(tmp_path, "matched", 1), [])
    _write_labels(
        tmp_path / "labels.csv",
        [
            ["1", "unanchored_external", "ext001", "unanchored_noise", ""],
            ["1", "unanchored_loop", "loop001", "unanchored_loop_keep", ""],
        ],
    )

    out = _run(tmp_path)
    assert "unanchored_external / unanchored_noise: 1" in out
    assert "unanchored_loop / unanchored_loop_keep: 1" in out


def test_report_separates_unanchored(tmp_path):
    (tmp_path / "corpus").mkdir()
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                loop_findings_unanchored=[{"summary": "ci passed"}],
                external_findings=[
                    {"file": None, "line": None, "summary": "overall LGTM", "source": "copilot"},
                ],
            )
        )
    )
    _write_jsonl(_jsonl_path(tmp_path, "unmatched", 1), [])
    _write_jsonl(_jsonl_path(tmp_path, "matched", 1), [])
    _write_labels(tmp_path / "labels.csv", [])

    out = _run(tmp_path)
    assert "Unanchored" in out
    # Unanchored externals counted in totals
    assert "1 unanchored" in out or "unanchored, 1" in out or "unanchored" in out


def test_report_includes_near_miss_section_sorted_desc_and_capped(tmp_path):
    """Phase 1 diagnostic: REPORT.md surfaces unmatched externals whose
    same-file loop finding scored highest, sorted desc, capped at 25."""
    output = _render_with_unmatched_records(
        tmp_path,
        unmatched=[
            {
                "finding_id": f"fid{i:02d}",
                "external": {"file": "x.py", "line": i, "summary": f"summary {i}"},
                "best_near_miss_score": i / 30.0,
                "best_near_miss_loop_summary": f"loop summary {i}",
                "best_near_miss_line_delta": 0,
            }
            for i in range(30)
        ],
    )
    assert "## Matcher near-misses" in output
    near_miss_section = output.split("## Matcher near-misses", 1)[1].split("## ", 1)[0]
    # Capped at 25 rows: count list-item lines.
    rows = [ln for ln in near_miss_section.splitlines() if ln.startswith("- ")]
    assert len(rows) == 25, f"expected 25 rows (cap), got {len(rows)}"
    # Sorted descending: extract scores from rendered rows (format is parser's choice;
    # this test asserts on monotonicity, not exact format).
    scores = [float(ln.split("score=")[1].split()[0]) for ln in rows if "score=" in ln]
    assert scores == sorted(scores, reverse=True), (
        f"near-miss section not sorted desc; scores: {scores}"
    )


def test_report_near_miss_section_flags_real_miss_labels(tmp_path):
    """Rows labeled real_miss in labels.csv get a visual flag.

    Routes labels through `_render_with_unmatched_records(..., labels_rows=...)`
    so the owner/repo/pr in the labels.csv row are guaranteed to match the
    corpus the helper writes (DEFAULT_OWNER, DEFAULT_REPO, pr=1). Open-coding
    `labels_csv.write_text(...)` with mismatched owner/repo/pr was the
    original bug this helper structure prevents.
    """
    output = _render_with_unmatched_records(
        tmp_path,
        unmatched=[
            {
                "finding_id": "fid01",
                "external": {"file": "x.py", "line": 1, "summary": "summary one"},
                "best_near_miss_score": 0.55,
                "best_near_miss_loop_summary": "loop summary one",
                "best_near_miss_line_delta": 0,
            }
        ],
        labels_rows=[(1, "unmatched", "fid01", "real_miss", "")],
    )
    near_miss_section = output.split("## Matcher near-misses", 1)[1].split("## ", 1)[0]
    assert "[real_miss]" in near_miss_section


def test_report_skips_near_miss_section_when_all_scores_null(tmp_path):
    """If no unmatched record has a same-file loop finding, omit the section
    entirely (no empty header)."""
    output = _render_with_unmatched_records(
        tmp_path,
        unmatched=[
            {
                "finding_id": "fid01",
                "external": {"file": "x.py", "line": 1, "summary": "summary"},
                "best_near_miss_score": None,
                "best_near_miss_loop_summary": None,
                "best_near_miss_line_delta": None,
            }
        ],
    )
    assert "## Matcher near-misses" not in output


def test_report_near_miss_section_floats_real_miss_above_25_row_cap(tmp_path):
    """Labeled real_miss rows must appear in the rendered (capped) section even
    when their score is below 25 higher-scoring unlabeled rows.

    Pins the (is_real_miss desc, score desc) sort key at report.py:454. A
    future change that drops the `-int(r.is_real_miss)` term from the sort key
    would silently drop labeled real_miss off the visible 25: corrupting the
    Phase 1 decision-rule input the section exists to surface.
    """
    # 28 unlabeled high-score rows + 2 labeled real_miss low-score rows.
    # Without the is_real_miss sort priority, both real_miss rows would be
    # cut off by the 25-row cap (their scores are below all 28 unlabeled).
    unmatched = [
        {
            "finding_id": f"fid_hi_{i:02d}",
            "external": {"file": "x.py", "line": 100 + i, "summary": f"hi summary {i}"},
            "best_near_miss_score": 0.30 + i * 0.005,  # 0.300..0.435: all unlabeled
            "best_near_miss_loop_summary": f"hi loop {i}",
            "best_near_miss_line_delta": 0,
        }
        for i in range(28)
    ]
    unmatched.extend(
        [
            {
                "finding_id": "fid_rm_a",
                "external": {"file": "x.py", "line": 1, "summary": "rm summary a"},
                "best_near_miss_score": 0.05,  # well below all unlabeled
                "best_near_miss_loop_summary": "rm loop a",
                "best_near_miss_line_delta": 0,
            },
            {
                "finding_id": "fid_rm_b",
                "external": {"file": "x.py", "line": 2, "summary": "rm summary b"},
                "best_near_miss_score": 0.07,
                "best_near_miss_loop_summary": "rm loop b",
                "best_near_miss_line_delta": 0,
            },
        ]
    )
    output = _render_with_unmatched_records(
        tmp_path,
        unmatched=unmatched,
        labels_rows=[
            (1, "unmatched", "fid_rm_a", "real_miss", ""),
            (1, "unmatched", "fid_rm_b", "real_miss", ""),
        ],
    )
    near_miss_section = output.split("## Matcher near-misses", 1)[1].split("## ", 1)[0]
    rows = [ln for ln in near_miss_section.splitlines() if ln.startswith("- ")]
    assert len(rows) == 25, f"expected 25 rows (cap), got {len(rows)}"
    # Both real_miss rows must appear despite their scores being below the cap.
    real_miss_rows = [ln for ln in rows if "[real_miss]" in ln]
    assert len(real_miss_rows) == 2, (
        f"both real_miss rows must float above the 25-row cap; saw {len(real_miss_rows)}: "
        f"{real_miss_rows}"
    )


def test_report_near_miss_section_renders_decision_rule_statistic_and_histogram(tmp_path):
    """The Phase 1 decision-rule statistic line and the real_miss score
    histogram are the diagnostic outputs the section exists to ship.

    Pins report.py:418-451: a regression that drops the statistic line,
    miscounts rm_ge_045, swaps bin edges, or skips the histogram block would
    currently pass every other test but corrupt the Phase 1 decision-rule
    verdict: the PR's stated purpose.
    """
    # 5 real_miss rows: 3 with score >= 0.45, 2 below. Decision-rule = 60.0%.
    # Bin distribution: [0.00-0.10):0, [0.10-0.20):1 (0.10), [0.20-0.30):1 (0.20),
    # [0.30-0.40):0, [0.40-0.45):0, [0.45-0.50):2 (0.45, 0.49), [0.50-0.75):1 (0.55).
    unmatched = [
        {
            "finding_id": f"rm_{i:02d}",
            "external": {"file": "x.py", "line": i, "summary": f"rm summary {i}"},
            "best_near_miss_score": score,
            "best_near_miss_loop_summary": f"rm loop {i}",
            "best_near_miss_line_delta": 0,
        }
        for i, score in enumerate([0.10, 0.20, 0.45, 0.49, 0.55])
    ]
    output = _render_with_unmatched_records(
        tmp_path,
        unmatched=unmatched,
        labels_rows=[(1, "unmatched", f"rm_{i:02d}", "real_miss", "") for i in range(5)],
    )
    near_miss_section = output.split("## Matcher near-misses", 1)[1].split("## ", 1)[0]
    # Decision-rule statistic line.
    assert "3 of 5 real_miss rows have score >= 0.45 (60.0%)" in near_miss_section, (
        f"decision-rule line missing or wrong; section:\n{near_miss_section}"
    )
    # Histogram header.
    assert "Real_miss near-miss score distribution (n=5):" in near_miss_section
    # Spot-check key bin edges including the 0.45 cut.
    assert "[0.10-0.20): 1" in near_miss_section
    assert "[0.20-0.30): 1" in near_miss_section
    assert "[0.45-0.50): 2" in near_miss_section
    assert "[0.50-0.75): 1" in near_miss_section


def test_report_near_miss_histogram_includes_line_gate_only_bin(tmp_path):
    """`_best_near_miss` deliberately applies no line gate, so a same-file loop
    finding far from the external with a near-identical summary can produce a
    near-miss score at or above CONTAINMENT_THRESHOLD. The histogram must carry
    bins covering that range so these line-gate-only rows are counted; without
    them, bin counts would not sum to n and a load-bearing diagnostic signal
    would be silently dropped.

    Pins report.py's bin list against a regression that removes the final
    bins or rebounds them short of 1.0.
    """
    # 3 real_miss rows: scores 0.65, 0.80, 1.00: all line-gate-only.
    unmatched = [
        {
            "finding_id": f"rm_{i:02d}",
            "external": {"file": "x.py", "line": i, "summary": f"rm summary {i}"},
            "best_near_miss_score": score,
            "best_near_miss_loop_summary": f"rm loop {i}",
            "best_near_miss_line_delta": 90,  # outside the match window, far line
        }
        for i, score in enumerate([0.65, 0.80, 1.00])
    ]
    output = _render_with_unmatched_records(
        tmp_path,
        unmatched=unmatched,
        labels_rows=[(1, "unmatched", f"rm_{i:02d}", "real_miss", "") for i in range(3)],
    )
    near_miss_section = output.split("## Matcher near-misses", 1)[1].split("## ", 1)[0]
    assert "Real_miss near-miss score distribution (n=3):" in near_miss_section
    # 0.65 lands in [0.50-0.75); 0.80 and 1.00 in [0.75-1.01). Both bins are
    # line-gate-only territory now that the match gate is CONTAINMENT_THRESHOLD.
    assert "[0.50-0.75): 1" in near_miss_section, (
        f"line-gate-only bin missing or miscounted; section:\n{near_miss_section}"
    )
    assert "[0.75-1.01): 2" in near_miss_section, (
        f"top line-gate-only bin missing or miscounted; section:\n{near_miss_section}"
    )


def test_report_near_miss_renders_when_line_delta_field_absent(tmp_path):
    """Back-compat: older harness JSONL has best_near_miss_score but no
    best_near_miss_line_delta key. report.py reads via .get(...) so the row
    must still render: with the `line_delta=` segment suppressed.

    Pins report.py:315 (`u.get('best_near_miss_line_delta')  # may be None on
    older JSONL`) and report.py:464 (the conditional `line_delta_str`). A
    regression that switched .get to subscript access would silently break
    older-JSONL handling and still pass every other test, since all other
    fixtures pass an explicit integer line_delta.
    """
    output = _render_with_unmatched_records(
        tmp_path,
        unmatched=[
            {
                "finding_id": "fid01",
                "external": {"file": "x.py", "line": 1, "summary": "summary one"},
                "best_near_miss_score": 0.42,
                "best_near_miss_loop_summary": "loop summary one",
                # best_near_miss_line_delta: intentionally absent
            }
        ],
    )
    assert "## Matcher near-misses" in output, "section must still render"
    near_miss_section = output.split("## Matcher near-misses", 1)[1].split("## ", 1)[0]
    rows = [ln for ln in near_miss_section.splitlines() if ln.startswith("- ")]
    assert len(rows) == 1
    assert "score=0.42" in rows[0]
    # line_delta segment must be omitted (not rendered as `line_delta=None`).
    assert "line_delta=" not in rows[0], (
        f"line_delta segment must be suppressed when field is absent; row: {rows[0]}"
    )


def test_report_near_miss_diagnostic_suppressed_when_no_real_miss_labels(tmp_path):
    """When near_miss_rows is non-empty but no rows are labeled real_miss, the
    decision-rule sentence must NOT claim a verdict on a zero denominator.

    Pins report.py:419: rendering "0 of 0 real_miss rows ... (0.0%) ... matcher
    recall is meaningfully limiting" reads as a falsified verdict on an
    unlabeled corpus. The "not computable" message must appear instead.
    """
    output = _render_with_unmatched_records(
        tmp_path,
        unmatched=[
            {
                "finding_id": "fid01",
                "external": {"file": "x.py", "line": 1, "summary": "summary"},
                "best_near_miss_score": 0.42,
                "best_near_miss_loop_summary": "loop summary",
                "best_near_miss_line_delta": 0,
            }
        ],
        # No labels_rows -> no real_miss labels on the row.
    )
    near_miss_section = output.split("## Matcher near-misses", 1)[1].split("## ", 1)[0]
    assert "decision-rule statistic is not computable" in near_miss_section, (
        f"must emit 'not computable' message when rm_total=0; section:\n{near_miss_section}"
    )
    assert "0 of 0" not in near_miss_section, (
        "must NOT render '0 of 0 ... matcher recall is meaningfully limiting' on zero denominator"
    )
    # Histogram block must also be suppressed (it was already gated on rm_total).
    assert "score distribution" not in near_miss_section


def test_candidate_cause_groups_correctness_summaries():
    """generic schema and failure tokens must not hide correctness findings."""
    # b7afe29bdb71: routed to "type design" on a bare `schema` token.
    assert "correctness" in _candidate_cause(
        "`EXPECTED_SCHEMA_ID_PREFIX` is hard-coded to the major.minor.patch directory"
    )
    # ebf2e7b79f2b: unguarded None.get().
    assert "correctness" in _candidate_cause(
        "`yaml.safe_load()` can return None (empty frontmatter) or a non-mapping type"
    )
    # ae6e19ba7827: routed to "type design"; it is a detection bypass.
    assert "correctness" in _candidate_cause(
        "`is_shallow()` treats any non-empty list as sufficient, which allows a bypass"
    )


def test_candidate_cause_keeps_genuine_type_design_summaries():
    """Phrase-restricting `schema` must not cost the real type-design findings."""
    assert "type design" in _candidate_cause(
        "the schema doesn't enforce the documented cap on adversary runs"
    )
    assert "type design" in _candidate_cause(
        "schema allows additionalProperties where the contract forbids them"
    )
    assert "type design" in _candidate_cause(
        "the schema does not express the documented mutual exclusion"
    )


def test_candidate_cause_gives_security_precedence_over_correctness():
    """generic correctness keys such as "bypass" also occur in security findings."""
    assert "security" in _candidate_cause("auth bypass due to a missing check")
    assert "security" in _candidate_cause("authentication bypass allows unauthenticated access")
    assert "security" in _candidate_cause("authorization check missing on the new endpoint")
    # Non-security uses of the same key stay on correctness.
    assert "correctness" in _candidate_cause(
        "`is_shallow()` treats any non-empty list as sufficient, which allows a bypass"
    )


def test_candidate_cause_yields_looseness_keys_to_schema_subjects():
    """Correctness's generic looseness keys ("too loose"/"too permissive") also
    describe schema constraints, so a schema *subject* routes to type design while
    a loose check stays on correctness."""
    assert "type design" in _candidate_cause(
        "the schema is too permissive and allows invalid blockers"
    )
    assert "correctness" in _candidate_cause("version-prefix check too loose")
    # A schema-shaped identifier is not a schema subject: EXPECTED_SCHEMA_ID_PREFIX
    # appears in a correctness finding about a hard-coded path.
    assert "correctness" in _candidate_cause(
        "`EXPECTED_SCHEMA_ID_PREFIX` is hard-coded to the major.minor.patch directory"
    )


def test_report_rejects_matcher_output_scored_by_a_different_scorer(tmp_path):
    """A4 interprets near-miss scores against containment bins and the 0.45 cut.

    Matcher output from before the containment switch partitions the same corpus
    into the same counts, so the count-based staleness check passes it while the
    scores are on the jaccard scale. Reading those as containment is silently
    wrong, so refuse rather than render.
    """
    (tmp_path / "corpus").mkdir()
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                external_findings=[{"file": "a.py", "line": 1, "summary": "s"}],
            )
        )
    )
    _write_jsonl(
        _jsonl_path(tmp_path, "unmatched", 1),
        [
            {
                "scorer": "token_overlap",
                "finding_id": "stale1",
                "external": {"file": "a.py", "line": 1, "summary": "s"},
                "best_near_miss_score": 0.55,
                "best_near_miss_loop_summary": "loop",
                "best_near_miss_line_delta": 2,
            }
        ],
    )
    _write_jsonl(_jsonl_path(tmp_path, "matched", 1), [])
    _write_labels(tmp_path / "labels.csv", [])

    with pytest.raises(subprocess.CalledProcessError) as exc:
        _run(tmp_path)
    assert "token_overlap" in exc.value.stderr
    assert "Re-run A2" in exc.value.stderr


def test_report_rejects_output_scored_at_a_different_threshold(tmp_path):
    """The stamp carries the threshold and window, not just the function name.

    A4 draws the overlap-gate/line-gate boundary at CONTAINMENT_THRESHOLD, so
    output scored by the same function at a different threshold is on a
    different scale. A bare function name would read as valid here.
    """
    (tmp_path / "corpus").mkdir()
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(1, external_findings=[{"file": "a.py", "line": 1, "summary": "s"}])
        )
    )
    _write_jsonl(
        _jsonl_path(tmp_path, "unmatched", 1),
        [
            {
                "scorer": "token_containment@0.6/win15",
                "finding_id": "drift1",
                "external": {"file": "a.py", "line": 1, "summary": "s"},
                "best_near_miss_score": 0.55,
                "best_near_miss_loop_summary": "loop",
                "best_near_miss_line_delta": 2,
            }
        ],
    )
    _write_jsonl(_jsonl_path(tmp_path, "matched", 1), [])
    _write_labels(tmp_path / "labels.csv", [])

    with pytest.raises(subprocess.CalledProcessError) as exc:
        _run(tmp_path)
    assert "token_containment@0.6/win15" in exc.value.stderr
    assert "Re-run A2" in exc.value.stderr


def _write_loop_unmatched(tmp_path, pr, records):
    path = _jsonl_path(tmp_path, "loop_unmatched", pr)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))


def _loop_record(fid, summary="a loop finding nobody else raised"):
    return {
        "finding_id": fid,
        "loop_finding": {"file": "a.ts", "line": 1, "summary": summary},
        "scorer": "token_containment@0.5/win15",
    }


def test_useful_rate_separates_low_value_and_corroboration(tmp_path):
    judgments = (
        ["loop_true_positive"] * 3
        + ["loop_low_value"] * 5
        + ["loop_false_positive"] * 2
        + ["loop_unjudgeable"] * 2
        + [""] * 4
    )
    records = [_loop_record(f"manual-{i}", f"finding {i}") for i in range(len(judgments))]
    corroborated = [
        {"file": f"matched-{i}.py", "line": 1, "summary": f"matched finding {i}"} for i in range(2)
    ]
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                loop_findings=[r["loop_finding"] for r in records] + corroborated,
                external_findings=corroborated,
            )
        )
    )
    _write_jsonl(
        _jsonl_path(tmp_path, "matched", 1),
        [
            {"finding_id": f"matched-{i}", "external": finding, "matched_loop": finding}
            for i, finding in enumerate(corroborated)
        ],
    )
    _write_jsonl(_jsonl_path(tmp_path, "unmatched", 1), [])
    _write_loop_unmatched(tmp_path, 1, records)
    _write_labels(
        tmp_path / "labels.csv",
        [
            (1, "loop_unmatched", record["finding_id"], label, "manual judgment")
            for record, label in zip(records, judgments, strict=True)
            if label
        ],
    )

    out = _run(tmp_path)

    assert "PIPELINE WARNING" not in out
    assert "Precision: 83.3% (10/12)" in out
    assert "Useful rate among manually judged, uncorroborated loop findings: 30.0% (3/10)" in out
    assert "Manual judgment coverage: 62.5% (10/16)" in out
    assert "- loop_true_positive: 3" in out
    assert "- loop_low_value: 5" in out
    assert "- loop_false_positive: 2" in out


@pytest.mark.parametrize("corroborated_count", [0, 2])
def test_useful_rate_without_manual_judgments_is_unmeasured(tmp_path, corroborated_count):
    corroborated = [
        {"file": f"matched-{i}.py", "line": 1, "summary": f"matched finding {i}"}
        for i in range(corroborated_count)
    ]
    records = [] if corroborated_count else [_loop_record("unlabeled")]
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                loop_findings=corroborated + [r["loop_finding"] for r in records],
                external_findings=corroborated,
            )
        )
    )
    _write_jsonl(
        _jsonl_path(tmp_path, "matched", 1),
        [
            {"finding_id": f"matched-{i}", "external": finding, "matched_loop": finding}
            for i, finding in enumerate(corroborated)
        ],
    )
    _write_jsonl(_jsonl_path(tmp_path, "unmatched", 1), [])
    _write_loop_unmatched(tmp_path, 1, records)
    _write_labels(tmp_path / "labels.csv", [])

    out = _run(tmp_path)

    assert "PIPELINE WARNING" not in out
    assert "Useful rate among manually judged, uncorroborated loop findings: n/a" in out
    if corroborated_count:
        assert "Precision: 100.0% (2/2)" in out
        assert "Manual judgment coverage: n/a, no uncorroborated loop findings" in out
    else:
        assert "Manual judgment coverage: 0.0% (0/1)" in out


def test_precision_counts_corroborated_and_hand_labeled(tmp_path):
    """Denominator is corroborated + the three judged labels. Corroborated pairs
    count as true positives: an issue an external reviewer also raised is real."""
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                loop_findings=[{"file": "a.ts", "line": 1, "summary": "s"}],
                external_findings=[
                    {"file": "a.ts", "line": 1, "summary": "s", "source": "copilot"}
                ],
            )
        )
    )
    _jsonl_path(tmp_path, "matched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "matched", 1).write_text(
        json.dumps(
            {
                "finding_id": "aaa",
                "external": {"file": "a.ts", "line": 1, "summary": "s"},
                "matched_loop": {"file": "a.ts", "line": 1, "summary": "s"},
                "scorer": "token_containment@0.5/win15",
            },
            sort_keys=True,
        )
        + "\n"
    )
    _jsonl_path(tmp_path, "unmatched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "unmatched", 1).write_text("")
    _write_loop_unmatched(tmp_path, 1, [_loop_record("t1"), _loop_record("f1"), _loop_record("u1")])
    _write_labels(
        tmp_path / "labels.csv",
        [
            (1, "matched_sample", "aaa", "matched_true", ""),
            (1, "loop_unmatched", "t1", "loop_true_positive", ""),
            (1, "loop_unmatched", "f1", "loop_false_positive", ""),
            (1, "loop_unmatched", "u1", "loop_unjudgeable", ""),
        ],
    )
    out = _run(tmp_path)
    # 1 corroborated + 1 true + 1 false judged; unjudgeable excluded => 2/3.
    assert "Precision: 66.7% (2/3)" in out
    assert "unjudgeable" in out


def test_precision_omitted_when_nothing_is_judged(tmp_path):
    """A percentage over an empty denominator reads as a measured result. The
    zero-denominator `matched_false rate: 0.0%` this replaces did exactly that."""
    _corpus_path(tmp_path, 1).write_text(json.dumps(_corpus_record(1)))
    _jsonl_path(tmp_path, "matched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "matched", 1).write_text("")
    _jsonl_path(tmp_path, "unmatched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "unmatched", 1).write_text("")
    _write_loop_unmatched(tmp_path, 1, [_loop_record("x1")])
    _write_labels(tmp_path / "labels.csv", [])
    out = _run(tmp_path)
    assert "Precision: n/a: no loop findings judged yet" in out
    assert "1 loop finding(s) unlabeled" in out


def test_precision_reports_coverage_against_the_full_population(tmp_path):
    """A percentage over a handful of judged findings reads as a property of the
    panel unless the report says how little of the population it covers."""
    _corpus_path(tmp_path, 1).write_text(json.dumps(_corpus_record(1)))
    _jsonl_path(tmp_path, "matched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "matched", 1).write_text("")
    _jsonl_path(tmp_path, "unmatched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "unmatched", 1).write_text("")
    _write_loop_unmatched(tmp_path, 1, [_loop_record(f"x{i}") for i in range(9)])
    _write_labels(tmp_path / "labels.csv", [(1, "loop_unmatched", "x0", "loop_true_positive", "")])
    out = _run(tmp_path)
    assert "Precision: 100.0% (1/1)" in out
    assert "11.1% of 9 loop finding(s)" in out


@pytest.mark.parametrize("rejected_first", [False, True])
def test_corroborated_counts_loop_findings_not_matched_pairs(tmp_path, rejected_first):
    """A2 writes one matched row per external, so two comments on the same loop
    finding produce two rows. Precision is defined over loop findings, so counting
    rows inflates both the numerator and the population."""
    loop_finding = {"file": "a.ts", "line": 1, "summary": "s"}
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                loop_findings=[loop_finding],
                external_findings=[
                    {"file": "a.ts", "line": 1, "summary": "x", "source": "copilot"},
                    {"file": "a.ts", "line": 1, "summary": "y", "source": "copilot"},
                ],
            )
        )
    )
    _jsonl_path(tmp_path, "matched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "matched", 1).write_text(
        "".join(
            json.dumps(
                {
                    "finding_id": fid,
                    "external": {"file": "a.ts", "line": 1, "summary": fid},
                    "matched_loop": loop_finding,
                    "scorer": "token_containment@0.5/win15",
                },
                sort_keys=True,
            )
            + "\n"
            for fid in ("e1", "e2")
        )
    )
    _jsonl_path(tmp_path, "unmatched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "unmatched", 1).write_text("")
    _write_loop_unmatched(tmp_path, 1, [])
    labels = [(1, "matched_sample", "e1", "matched_false", "")] if rejected_first else []
    _write_labels(tmp_path / "labels.csv", labels)
    out = _run(tmp_path)
    assert "Precision: 100.0% (1/1)" in out
    assert "corroborated by an external reviewer: 1" in out
    assert "Judged 100.0% of 1 loop finding(s)" in out


def test_loop_side_invariant_flags_stale_a2_output(tmp_path):
    """_load_jsonl treats a missing loop_unmatched file as an empty bucket, so
    pre-change A2 output would publish precision over matched rows alone with
    every uncorroborated loop finding silently absent."""
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                loop_findings=[
                    {"file": "a.ts", "line": 1, "summary": "one"},
                    {"file": "b.ts", "line": 2, "summary": "two"},
                ],
            )
        )
    )
    _jsonl_path(tmp_path, "matched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "matched", 1).write_text("")
    _jsonl_path(tmp_path, "unmatched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "unmatched", 1).write_text("")
    # No loop_unmatched file at all: exactly what stale A2 output looks like.
    _write_labels(tmp_path / "labels.csv", [])
    out = _run(tmp_path)
    assert "PIPELINE WARNING" in out
    assert "loop findings" in out


@pytest.mark.parametrize(
    ("loop_label", "precision", "coverage"),
    [
        (None, "100.0% (1/1)", "50.0% of 2"),
        ("loop_false_positive", "50.0% (1/2)", "100.0% of 2"),
        ("loop_true_positive", "100.0% (2/2)", "100.0% of 2"),
    ],
)
def test_rejected_pair_remains_in_the_precision_population(
    tmp_path, loop_label, precision, coverage
):
    """A `matched_false` label says the pair should not have been made, so its
    loop side was never corroborated. Counting it anyway credits the panel for a
    catch the labeler explicitly rejected."""
    true_loop = {"file": "a.ts", "line": 1, "summary": "real"}
    false_loop = {"file": "b.ts", "line": 2, "summary": "bogus"}
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                loop_findings=[true_loop, false_loop],
                external_findings=[
                    {"file": "a.ts", "line": 1, "summary": "x", "source": "copilot"},
                    {"file": "b.ts", "line": 2, "summary": "y", "source": "copilot"},
                ],
            )
        )
    )
    _jsonl_path(tmp_path, "matched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "matched", 1).write_text(
        "".join(
            json.dumps(
                {
                    "finding_id": fid,
                    "external": {"file": lf["file"], "line": lf["line"], "summary": fid},
                    "matched_loop": lf,
                    "scorer": "token_containment@0.5/win15",
                },
                sort_keys=True,
            )
            + "\n"
            for fid, lf in (("aaa", true_loop), ("bbb", false_loop))
        )
    )
    _jsonl_path(tmp_path, "unmatched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "unmatched", 1).write_text("")
    _write_loop_unmatched(tmp_path, 1, [])
    labels = [
        (1, "matched_sample", "aaa", "matched_true", ""),
        (1, "matched_sample", "bbb", "matched_false", ""),
    ]
    if loop_label is not None:
        labels.append((1, "loop_unmatched", finding_id(false_loop), loop_label, ""))
    _write_labels(tmp_path / "labels.csv", labels)
    out = _run(tmp_path)
    assert "corroborated by an external reviewer: 1" in out
    assert f"Precision: {precision}" in out
    assert f"Judged {coverage} loop finding(s)" in out
    assert "PIPELINE WARNING" not in out


def test_matched_false_label_does_not_trip_the_loop_invariant(tmp_path):
    """The invariant checks A2's structural output against the corpus. Dropping a
    labeled-false pair from the corroborated set is a scoring decision, so folding
    it into the invariant would report stale A2 output for a labeling act."""
    loop_finding = {"file": "b.ts", "line": 2, "summary": "bogus"}
    _corpus_path(tmp_path, 1).write_text(
        json.dumps(
            _corpus_record(
                1,
                loop_findings=[loop_finding],
                external_findings=[
                    {"file": "b.ts", "line": 2, "summary": "y", "source": "copilot"}
                ],
            )
        )
    )
    _jsonl_path(tmp_path, "matched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "matched", 1).write_text(
        json.dumps(
            {
                "finding_id": "bbb",
                "external": {"file": "b.ts", "line": 2, "summary": "y"},
                "matched_loop": loop_finding,
                "scorer": "token_containment@0.5/win15",
            },
            sort_keys=True,
        )
        + "\n"
    )
    _jsonl_path(tmp_path, "unmatched", 1).parent.mkdir(parents=True, exist_ok=True)
    _jsonl_path(tmp_path, "unmatched", 1).write_text("")
    _write_loop_unmatched(tmp_path, 1, [])
    _write_labels(tmp_path / "labels.csv", [(1, "matched_sample", "bbb", "matched_false", "")])
    out = _run(tmp_path)
    assert "stale loop-side matcher outputs" not in out
