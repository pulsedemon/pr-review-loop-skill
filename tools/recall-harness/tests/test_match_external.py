"""Tests for match_external bucketing. Uses real match_findings.py."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1]
SCRIPT = HARNESS / "match_external.py"
MATCH_SCRIPT = HARNESS.parent.parent / "scripts" / "match_findings.py"

from collect_pr_corpus import (  # type: ignore[import-not-found]  # noqa: E402  — sibling made importable by conftest.py
    CORPUS_VERSION,
    corpus_filename,
    matched_filename,
)
from match_external import (  # type: ignore[import-not-found]  # noqa: E402  — sibling made importable by conftest.py
    _load_matcher,
    _run_matcher,
)


def _run(corpus: dict, tmp_path: Path) -> dict:
    """Invoke match_external on a single in-memory corpus, return parsed buckets."""
    corpus_dir = tmp_path / "corpus"
    unmatched_dir = tmp_path / "unmatched"
    matched_dir = tmp_path / "matched"
    loop_unmatched_dir = tmp_path / "loop_unmatched"
    corpus_dir.mkdir()
    corpus_path = corpus_dir / corpus_filename(corpus["owner"], corpus["repo"], corpus["pr"])
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    corpus_path.write_text(json.dumps(corpus, indent=2, sort_keys=True))
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--corpus-dir",
            str(corpus_dir),
            "--unmatched-dir",
            str(unmatched_dir),
            "--matched-dir",
            str(matched_dir),
            "--loop-unmatched-dir",
            str(loop_unmatched_dir),
            "--match-script",
            str(MATCH_SCRIPT),
        ],
        check=True,
    )
    jsonl_name = matched_filename(corpus["owner"], corpus["repo"], corpus["pr"])
    unmatched_path = unmatched_dir / jsonl_name
    matched_path = matched_dir / jsonl_name
    loop_unmatched_path = loop_unmatched_dir / jsonl_name
    unmatched = (
        [json.loads(line) for line in unmatched_path.read_text().splitlines() if line.strip()]
        if unmatched_path.exists()
        else []
    )
    matched = (
        [json.loads(line) for line in matched_path.read_text().splitlines() if line.strip()]
        if matched_path.exists()
        else []
    )
    loop_unmatched = (
        [json.loads(line) for line in loop_unmatched_path.read_text().splitlines() if line.strip()]
        if loop_unmatched_path.exists()
        else []
    )
    return {"unmatched": unmatched, "matched": matched, "loop_unmatched": loop_unmatched}


def _corpus(loop, external, pr=1):
    return {
        "corpus_version": CORPUS_VERSION,
        "pr": pr,
        "owner": "o",
        "repo": "r",
        "title": "t",
        "merged_at": "2026-05-01T00:00:00Z",
        "merge_commit_sha": "abc",
        "head_sha_at_merge": "def",
        "base_ref": "main",
        "head_ref": "feat",
        "loop_findings": loop,
        "loop_findings_unanchored": [],
        "external_findings": external,
    }


def test_anchored_external_matches_anchored_loop(tmp_path):
    # Pins all three harness overrides, so none can silently revert.
    #
    # Delta 13: copilot anchors to its diff hunk while the loop cites its own
    # read, and a hand-verified corpus pair sits exactly here. A delta inside the
    # loop's ±5 would pass even with HARNESS_LINE_WINDOW dropped.
    #
    # Scores containment 0.500 and jaccard 0.200 at 8 tokens vs 16. Landing on
    # CONTAINMENT_THRESHOLD rather than comfortably above it is what pins the
    # threshold: a score of 0.75 would still match if `threshold` fell back to
    # OVERLAP_THRESHOLD. Reverting the scorer, the threshold, or the window each
    # drops this pair to unmatched.
    corpus = _corpus(
        loop=[
            {
                "file": "src/a.ts",
                "line": 10,
                "summary": "missing audit log on login for failed auth attempts here",
            }
        ],
        external=[
            {
                "file": "src/a.ts",
                "line": 23,
                "summary": (
                    "a failed login writes no audit entry here which leaves operators "
                    "unable to reconstruct the sequence from stored records afterwards"
                ),
                "source": "copilot",
                "id": 1,
                "created_at": "2026-05-02T00:00:00Z",
            }
        ],
    )
    out = _run(corpus, tmp_path)
    assert out["unmatched"] == []
    assert len(out["matched"]) == 1
    assert out["matched"][0]["external"]["id"] == 1
    assert out["matched"][0]["matched_loop"]["file"] == "src/a.ts"


def test_anchored_external_unmatched_when_no_loop_finding(tmp_path):
    corpus = _corpus(
        loop=[],
        external=[
            {
                "file": "src/a.ts",
                "line": 10,
                "summary": "missing timeout on fetch",
                "source": "copilot",
                "id": 2,
                "created_at": "2026-05-02T00:00:00Z",
            }
        ],
    )
    out = _run(corpus, tmp_path)
    assert len(out["unmatched"]) == 1
    assert out["unmatched"][0]["external"]["id"] == 2
    assert out["matched"] == []


def test_anchored_external_unmatched_when_loop_is_different_file(tmp_path):
    corpus = _corpus(
        loop=[
            {
                "file": "src/b.ts",
                "line": 10,
                "summary": "missing audit log on login for failed auth attempts here",
            }
        ],
        external=[
            {
                "file": "src/a.ts",
                "line": 10,
                "summary": "missing audit log on login",
                "source": "copilot",
                "id": 3,
                "created_at": "2026-05-02T00:00:00Z",
            }
        ],
    )
    out = _run(corpus, tmp_path)
    # Same summary but different file: matcher should not match.
    assert len(out["unmatched"]) == 1
    assert out["matched"] == []


def test_unanchored_external_bucketed_separately(tmp_path):
    corpus = _corpus(
        loop=[],
        external=[
            {
                "file": None,
                "line": None,
                "summary": "Overall LGTM",
                "source": "copilot",
                "id": 4,
                "created_at": "2026-05-02T00:00:00Z",
            }
        ],
    )
    out = _run(corpus, tmp_path)
    # Unanchored externals are excluded from both matched and unmatched.
    assert out["unmatched"] == []
    assert out["matched"] == []


def test_loop_finding_without_anchor_skipped(tmp_path):
    """A loop finding lacking file/line is never paired (matcher requires both)."""
    corpus = _corpus(
        loop=[
            {"file": None, "line": None, "summary": "ci item"},
            {
                "file": "src/a.ts",
                "line": 10,
                "summary": "real anchored loop finding about a missing timeout on the fetch call",
            },
        ],
        external=[
            {
                "file": "src/a.ts",
                "line": 10,
                "summary": "real anchored loop finding about a missing timeout on the fetch call",
                "source": "copilot",
                "id": 5,
                "created_at": "2026-05-02T00:00:00Z",
            }
        ],
    )
    out = _run(corpus, tmp_path)
    # Should match against the anchored loop finding, not error on the unanchored one.
    assert len(out["matched"]) == 1


def test_empty_corpus_produces_empty_outputs(tmp_path):
    corpus = _corpus(loop=[], external=[])
    out = _run(corpus, tmp_path)
    assert out["unmatched"] == []
    assert out["matched"] == []


def test_is_open_corpus_skipped_no_matched_or_unmatched_emitted(tmp_path):
    """In-flight (is_open=True) corpora must be skipped by A2 so they don't leave
    stale matched/unmatched JSONL behind once the PR merges. report.py already
    excludes is_open records from totals; match_external.process_corpus_file
    must agree on the skip."""
    corpus = _corpus(
        loop=[{"file": "src/a.ts", "line": 10, "summary": "loop finding"}],
        external=[
            {
                "file": "src/a.ts",
                "line": 10,
                "summary": "external finding that would match",
                "source": "copilot",
                "id": 99,
                "created_at": "2026-05-02T00:00:00Z",
            }
        ],
    )
    corpus["is_open"] = True
    out = _run(corpus, tmp_path)
    assert out["matched"] == []
    assert out["unmatched"] == []


@pytest.fixture(scope="module")
def matcher_module():
    return _load_matcher(MATCH_SCRIPT)


def _good():
    return {"file": "src/a.ts", "line": 10, "summary": "missing audit log"}


def test_run_matcher_raises_when_field_missing(matcher_module):
    bad = {"file": "src/a.ts", "line": 10}  # missing summary
    with pytest.raises(RuntimeError, match="missing required field 'summary'"):
        _run_matcher(matcher_module, _good(), bad)


def test_run_matcher_raises_when_line_is_string(matcher_module):
    bad = {"file": "src/a.ts", "line": "10", "summary": "x"}
    with pytest.raises(RuntimeError, match="field 'line' has wrong type"):
        _run_matcher(matcher_module, _good(), bad)


def test_run_matcher_raises_when_line_is_bool(matcher_module):
    """bool is a subclass of int in Python; the matcher explicitly excludes it
    so `True` doesn't sneak through as line number 1."""
    bad = {"file": "src/a.ts", "line": True, "summary": "x"}
    with pytest.raises(RuntimeError, match="field 'line' has wrong type"):
        _run_matcher(matcher_module, _good(), bad)


def test_run_matcher_raises_when_summary_is_not_string(matcher_module):
    bad = {"file": "src/a.ts", "line": 10, "summary": 42}
    with pytest.raises(RuntimeError, match="field 'summary' has wrong type"):
        _run_matcher(matcher_module, _good(), bad)


def test_run_matcher_raises_when_file_is_not_string(matcher_module):
    bad = {"file": 42, "line": 10, "summary": "x"}
    with pytest.raises(RuntimeError, match="field 'file' has wrong type"):
        _run_matcher(matcher_module, _good(), bad)


def test_run_matcher_validates_both_operands(matcher_module):
    """Each operand is validated independently — a malformed `a` raises with
    label 'a', a malformed `b` raises with label 'b'. Pins the label so a
    refactor that drops the per-operand naming would fail."""
    bad = {"file": "src/a.ts", "line": 10}  # missing summary
    with pytest.raises(RuntimeError, match="^matcher input a:"):
        _run_matcher(matcher_module, bad, _good())
    with pytest.raises(RuntimeError, match="^matcher input b:"):
        _run_matcher(matcher_module, _good(), bad)


def test_emitted_records_carry_the_scorer_stamp(tmp_path):
    """A4 refuses output scored by anything but its expected scorer, and that
    guard is only reachable if A2 stamps every record it writes."""
    corpus = _corpus(
        loop=[
            {
                "file": "src/a.ts",
                "line": 10,
                "summary": "missing audit log on login for failed auth attempts here",
            }
        ],
        external=[
            {
                "file": "src/a.ts",
                "line": 10,
                "summary": "missing audit log on login for failed auth attempts here",
                "source": "copilot",
                "id": 1,
                "created_at": "2026-05-02T00:00:00Z",
            },
            {
                "file": "src/b.ts",
                "line": 99,
                "summary": "an unrelated finding that will land in the unmatched bucket instead",
                "source": "copilot",
                "id": 2,
                "created_at": "2026-05-02T00:00:00Z",
            },
        ],
    )
    out = _run(corpus, tmp_path)
    assert len(out["matched"]) == 1
    assert len(out["unmatched"]) == 1
    for bucket in ("matched", "unmatched"):
        for rec in out[bucket]:
            assert rec.get("scorer") == "token_containment@0.5/win15", (
                f"{bucket} record missing the scorer stamp; report.py's guard "
                "cannot tell this output from pre-containment output"
            )


def test_loop_finding_matching_nothing_lands_in_loop_unmatched(tmp_path):
    """The precision bucket. A2 iterates externals and consults loop findings only
    as match candidates, so before this a loop finding nobody commented on was
    written nowhere and no labeling could reach it."""
    loop = [
        {
            "file": "a.ts",
            "line": 10,
            "summary": (
                "the retry helper swallows the timeout error and returns a default "
                "value, so callers cannot distinguish failure"
            ),
        },
        {"file": "b.ts", "line": 20, "summary": "unrelated finding nobody else raised at all"},
    ]
    external = [
        {
            "file": "a.ts",
            "line": 11,
            "summary": (
                "the retry helper swallows the timeout error and returns a default, "
                "so callers cannot distinguish a real value from a failure"
            ),
            "source": "copilot",
        }
    ]
    out = _run(_corpus(loop, external), tmp_path)
    assert len(out["matched"]) == 1
    assert [r["loop_finding"]["file"] for r in out["loop_unmatched"]] == ["b.ts"]


def test_loop_unmatched_records_carry_finding_id_and_scorer(tmp_path):
    """report.py joins labels on finding_id and hard-fails on any record whose
    scorer stamp differs, so a bucket missing either is unusable."""
    loop = [{"file": "b.ts", "line": 20, "summary": "unrelated finding nobody else raised at all"}]
    out = _run(_corpus(loop, []), tmp_path)
    (record,) = out["loop_unmatched"]
    assert len(record["finding_id"]) == 12
    assert record["scorer"] == "token_containment@0.5/win15"


def test_unanchored_loop_finding_absent_from_loop_unmatched(tmp_path):
    """Unanchored loop findings never reach the matcher, so calling them unmatched
    would report a miss the matcher was never given a chance to make."""
    loop = [{"summary": "a finding with no file or line anchor at all"}]
    out = _run(_corpus(loop, []), tmp_path)
    assert out["loop_unmatched"] == []
