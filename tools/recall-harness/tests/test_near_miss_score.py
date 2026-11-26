"""Tests for the best_near_miss_score field on unmatched records.

The matcher buckets findings as
matched/unmatched at CONTAINMENT_THRESHOLD against same-file loop findings
within HARNESS_LINE_WINDOW. This adds, for each unmatched record, the
highest-scoring same-file loop finding's overlap, so REPORT.md can surface
unmatched externals where a loop finding plausibly addresses the same thing but
fell below threshold. Highest-scoring, not nearest by line: `line_delta` is
reported for whichever finding wins on score.

Fixtures here carry summaries long enough to clear MIN_CONTAINMENT_TOKENS.
Containment reports 0.0 below that floor, so four-word summaries score zero against every candidate.

The `_best_near_miss` helper deliberately applies no line gate at all — the
whole point of the diagnostic is to see whether the line gate or the overlap
gate is what fired. `line_delta` is recorded separately on each record so the
reader can distinguish the two cases."""

import json
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
SCRIPT = HARNESS / "match_external.py"

from collect_pr_corpus import (  # type: ignore[import-not-found]  # noqa: E402
    corpus_filename,
    matched_filename,
)
from match_external import CORPUS_VERSION  # type: ignore[import-not-found]  # noqa: E402


def _run(corpus: dict, tmp_path: Path) -> tuple[list[dict], list[dict]]:
    """Invoke match_external on one in-memory corpus, return (matched, unmatched)."""
    corpus_dir = tmp_path / "corpus"
    unmatched_dir = tmp_path / "unmatched"
    matched_dir = tmp_path / "matched"
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
            "--loop-unmatched-dir",
            str(tmp_path / "loop_unmatched"),
            "--matched-dir",
            str(matched_dir),
        ],
        check=True,
    )
    name = matched_filename(corpus["owner"], corpus["repo"], corpus["pr"])
    matched = [
        json.loads(line) for line in (matched_dir / name).read_text().splitlines() if line.strip()
    ]
    unmatched = [
        json.loads(line) for line in (unmatched_dir / name).read_text().splitlines() if line.strip()
    ]
    return matched, unmatched


def _corpus(externals: list[dict], loop: list[dict]) -> dict:
    return {
        "corpus_version": CORPUS_VERSION,
        "owner": "pulsedemon",
        "repo": "pr-review-loop",
        "pr": 999,
        "external_findings": externals,
        "loop_findings": loop,
    }


def test_unmatched_record_has_best_near_miss_score_when_same_file_loop_exists(tmp_path):
    """Unmatched external + same-file loop finding => score is the containment overlap."""
    loop_summary = "schema is not validated when loaded from the incoming request body payload"
    corpus = _corpus(
        externals=[
            {
                "file": "foo.py",
                "line": 10,
                "summary": "validator does not check schema before use on the upload path",
            }
        ],
        loop=[
            {
                "file": "foo.py",
                "line": 12,
                "summary": loop_summary,
            }
        ],
    )
    _, unmatched = _run(corpus, tmp_path)
    assert len(unmatched) == 1
    rec = unmatched[0]
    assert "best_near_miss_score" in rec, "missing best_near_miss_score on unmatched record"
    assert isinstance(rec["best_near_miss_score"], float)
    # Exact, not a range: this pair scores jaccard 0.133 and containment 0.250,
    # and a `0 < s < 0.5` bound accepts both, so it would not catch
    # _best_near_miss reverting to token_overlap. The score has to stay on the
    # same scale as the match gate for the near-miss diagnostic to mean anything.
    assert rec["best_near_miss_score"] == 0.25, (
        f"expected the containment score; got {rec['best_near_miss_score']}"
    )
    assert rec.get("best_near_miss_loop_summary") == loop_summary
    # Line delta is informational: ext.line=10, loop.line=12 -> delta 2.
    assert rec["best_near_miss_line_delta"] == 2


def test_unmatched_record_has_null_near_miss_when_no_same_file_loop(tmp_path):
    """Unmatched external with no same-file loop finding => all three fields are None."""
    corpus = _corpus(
        externals=[
            {
                "file": "foo.py",
                "line": 10,
                "summary": "validator does not check schema",
            }
        ],
        loop=[
            {
                "file": "bar.py",
                "line": 10,
                "summary": "schema is not validated",
            }
        ],
    )
    _, unmatched = _run(corpus, tmp_path)
    assert unmatched[0]["best_near_miss_score"] is None
    assert unmatched[0]["best_near_miss_loop_summary"] is None
    assert unmatched[0]["best_near_miss_line_delta"] is None


def test_best_near_miss_uses_max_across_multiple_same_file_loop_findings(tmp_path):
    """If multiple loop findings share the file, report the maximum overlap.

    Also asserts line_delta tracks the *winning-by-score* finding, not the
    closest-by-line one — score is the primary key, line_delta is recorded
    as auxiliary signal so the reader can spot a high-score-far-line case.
    """
    # Summaries here clear MIN_CONTAINMENT_TOKENS: containment reports 0.0
    # below that floor, so a four-word fixture would score every candidate the
    # same and the max-wins assertion would pass vacuously.
    near = "schema validation is skipped for uploads received on the retry queue path"
    corpus = _corpus(
        externals=[
            {
                "file": "foo.py",
                "line": 10,
                "summary": "validator does not check schema before use in the handler path",
            }
        ],
        loop=[
            {
                "file": "foo.py",
                "line": 12,
                "summary": "completely unrelated topic about retry backoff timing configuration",
            },
            {"file": "foo.py", "line": 14, "summary": near},
        ],
    )
    _, unmatched = _run(corpus, tmp_path)
    assert unmatched[0]["best_near_miss_score"] is not None
    assert unmatched[0]["best_near_miss_loop_summary"] == near
    # Winner is loop.line=14 (higher overlap), so delta = abs(10-14) = 4 — NOT the
    # closer-by-line loop.line=12 (which has unrelated summary).
    assert unmatched[0]["best_near_miss_line_delta"] == 4


def test_best_near_miss_includes_loop_findings_beyond_line_window(tmp_path):
    """line-window misses still need an overlap score for diagnosis."""
    corpus = _corpus(
        externals=[
            {
                "file": "foo.py",
                "line": 10,
                "summary": "validator does not check schema before use on the upload path",
            }
        ],
        loop=[
            {
                "file": "foo.py",
                "line": 100,  # delta=90, far outside HARNESS_LINE_WINDOW
                "summary": "validator does not check schema before use on the upload path",
            }
        ],
    )
    _, unmatched = _run(corpus, tmp_path)
    rec = unmatched[0]
    # Identical summaries, so assert the actual 1.0 rather than just non-None:
    # `is not None` also passes on 0.0, which is what a below-floor fixture
    # scores, and that would let this test claim a high-overlap case it never
    # exercised.
    assert rec["best_near_miss_score"] == 1.0, (
        "score must be set for a same-file loop finding even when delta > the match window; "
        "_best_near_miss must NOT apply the matcher's line gate"
    )
    assert rec["best_near_miss_line_delta"] == 90
    assert (
        rec["best_near_miss_loop_summary"]
        == "validator does not check schema before use on the upload path"
    )


def test_below_floor_candidate_is_unscorable_not_a_zero(tmp_path):
    """`token_containment` returns 0.0 both for genuine zero overlap and for a
    pair it cannot judge. Only the first is a measurement.

    Serializing the second as 0.0 would put an unscorable row into report.py's
    decision-rule denominator as below-cut evidence, diluting a statistic with
    pairs nothing actually scored.
    """
    corpus = _corpus(
        externals=[
            {
                "file": "foo.py",
                "line": 10,
                "summary": "validator does not check the schema before use on the upload path",
            }
        ],
        loop=[{"file": "foo.py", "line": 12, "summary": "short one here"}],
    )
    _, unmatched = _run(corpus, tmp_path)
    assert unmatched[0]["best_near_miss_score"] is None, (
        "a candidate under MIN_CONTAINMENT_TOKENS is unscorable, not a zero score"
    )
    assert unmatched[0]["best_near_miss_loop_summary"] is None


def test_scorable_candidate_with_no_overlap_still_scores_zero(tmp_path):
    """The other half: a pair both sides of which clear the floor and share no
    tokens is a real measurement of zero, and must stay in the denominator."""
    zero_overlap = "completely different retry backoff timing configuration entirely here today"
    corpus = _corpus(
        externals=[
            {
                "file": "foo.py",
                "line": 10,
                "summary": "validator does not check the schema before use on the upload path",
            }
        ],
        loop=[{"file": "foo.py", "line": 12, "summary": zero_overlap}],
    )
    _, unmatched = _run(corpus, tmp_path)
    assert unmatched[0]["best_near_miss_score"] == 0.0
    assert unmatched[0]["best_near_miss_loop_summary"] == zero_overlap
