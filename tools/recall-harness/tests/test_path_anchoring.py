"""The three harness scripts default their dir args to absolute, script-anchored
paths so they run correctly from any cwd (running from inside tools/recall-harness/
must not produce a doubled tools/recall-harness/tools/recall-harness/... path)."""

from pathlib import Path

import collect_pr_corpus  # type: ignore[import-not-found]
import match_external  # type: ignore[import-not-found]
import report  # type: ignore[import-not-found]

HARNESS = Path(__file__).resolve().parents[1]
REPO_ROOT = HARNESS.parent.parent


def test_collect_default_out_dir_is_anchored():
    assert collect_pr_corpus.DEFAULT_OUT_DIR.is_absolute()
    assert collect_pr_corpus.DEFAULT_OUT_DIR == HARNESS / "corpus"


def test_match_external_default_dirs_are_anchored():
    assert match_external.DEFAULT_CORPUS_DIR == HARNESS / "corpus"
    assert match_external.DEFAULT_UNMATCHED_DIR == HARNESS / "unmatched"
    assert match_external.DEFAULT_MATCHED_DIR == HARNESS / "matched"
    assert match_external.DEFAULT_LOOP_UNMATCHED_DIR == HARNESS / "loop_unmatched"
    for p in (
        match_external.DEFAULT_CORPUS_DIR,
        match_external.DEFAULT_UNMATCHED_DIR,
        match_external.DEFAULT_MATCHED_DIR,
        match_external.DEFAULT_LOOP_UNMATCHED_DIR,
    ):
        assert p.is_absolute()


def test_match_external_match_script_anchored_to_repo_root():
    assert match_external.DEFAULT_MATCH_SCRIPT.is_absolute()
    assert match_external.DEFAULT_MATCH_SCRIPT == REPO_ROOT / "scripts" / "match_findings.py"
    assert match_external.DEFAULT_MATCH_SCRIPT.exists()


def test_report_default_dirs_are_anchored():
    assert report.DEFAULT_CORPUS_DIR == HARNESS / "corpus"
    assert report.DEFAULT_UNMATCHED_DIR == HARNESS / "unmatched"
    assert report.DEFAULT_MATCHED_DIR == HARNESS / "matched"
    assert report.DEFAULT_LOOP_UNMATCHED_DIR == HARNESS / "loop_unmatched"
    assert report.DEFAULT_LABELS == HARNESS / "labels.csv"
    for p in (
        report.DEFAULT_CORPUS_DIR,
        report.DEFAULT_UNMATCHED_DIR,
        report.DEFAULT_MATCHED_DIR,
        report.DEFAULT_LOOP_UNMATCHED_DIR,
        report.DEFAULT_LABELS,
    ):
        assert p.is_absolute()
