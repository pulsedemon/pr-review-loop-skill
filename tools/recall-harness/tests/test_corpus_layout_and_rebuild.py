"""Mixed flat+nested corpus must hard-fail (defense-in-depth + the PR #13 ask),
and match_external must rebuild matched/+unmatched/ so stale outputs can't
persist. The flat-ONLY case keeps its existing 'legacy flat corpus layout'
message (covered by test_version_and_schema_guards.py) and is not retested here."""

import json
import subprocess
import sys
from pathlib import Path

from collect_pr_corpus import (  # type: ignore[import-not-found]
    CORPUS_VERSION,
    corpus_filename,
)

HARNESS = Path(__file__).resolve().parents[1]
MATCH_SCRIPT_PATH = HARNESS / "match_external.py"
REPORT_SCRIPT_PATH = HARNESS / "report.py"
REPO_FINDING_MATCHER = HARNESS.parent.parent / "scripts" / "finding_matcher.py"


def _valid_corpus(owner: str, repo: str, pr: int) -> dict:
    return {
        "corpus_version": CORPUS_VERSION,
        "pr": pr,
        "owner": owner,
        "repo": repo,
        "title": "t",
        "merged_at": "2026-01-01T00:00:00Z",
        "merge_commit_sha": "abc",
        "head_sha_at_merge": "def",
        "base_ref": "main",
        "head_ref": "f",
        "is_open": False,
        "loop_findings": [],
        "loop_findings_unanchored": [],
        "external_findings": [],
    }


def _write_nested(corpus_dir: Path, owner: str, repo: str, pr: int) -> None:
    p = corpus_dir / corpus_filename(owner, repo, pr)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_valid_corpus(owner, repo, pr)))


def _run_match(
    corpus_dir: Path,
    unmatched: Path,
    matched: Path,
    loop_unmatched: Path | None = None,
) -> subprocess.CompletedProcess:
    # Always pass --loop-unmatched-dir: defaulted, A2 would write into the real
    # tools/recall-harness/loop_unmatched/ instead of the tmp tree.
    loop_unmatched = loop_unmatched or (corpus_dir.parent / "loop_unmatched")
    return subprocess.run(
        [
            sys.executable,
            str(MATCH_SCRIPT_PATH),
            "--corpus-dir",
            str(corpus_dir),
            "--unmatched-dir",
            str(unmatched),
            "--matched-dir",
            str(matched),
            "--loop-unmatched-dir",
            str(loop_unmatched),
            "--match-script",
            str(REPO_FINDING_MATCHER),
        ],
        capture_output=True,
        text=True,
    )


def test_match_external_rejects_mixed_layout(tmp_path):
    corpus_dir = tmp_path / "corpus"
    _write_nested(corpus_dir, "o", "r", 1)  # valid nested
    (corpus_dir / "pr-99.json").write_text("{}")  # stray flat
    result = _run_match(corpus_dir, tmp_path / "unmatched", tmp_path / "matched")
    assert result.returncode != 0
    assert "mixed corpus layout detected" in result.stderr


def test_report_rejects_mixed_layout(tmp_path):
    corpus_dir = tmp_path / "corpus"
    _write_nested(corpus_dir, "o", "r", 1)
    (corpus_dir / "pr-99.json").write_text("{}")
    (tmp_path / "labels.csv").write_text("owner,repo,pr,bucket,finding_id,label,notes\n")
    result = subprocess.run(
        [
            sys.executable,
            str(REPORT_SCRIPT_PATH),
            "--corpus-dir",
            str(corpus_dir),
            "--unmatched-dir",
            str(tmp_path / "unmatched"),
            "--matched-dir",
            str(tmp_path / "matched"),
            "--labels",
            str(tmp_path / "labels.csv"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "mixed corpus layout detected" in result.stderr


def test_match_external_rebuild_clears_stale_outputs(tmp_path):
    corpus_dir = tmp_path / "corpus"
    _write_nested(corpus_dir, "o", "r", 1)
    unmatched = tmp_path / "unmatched"
    matched = tmp_path / "matched"
    unmatched.mkdir()
    matched.mkdir()
    loop_unmatched = tmp_path / "loop_unmatched"
    loop_unmatched.mkdir()
    (unmatched / "stale-flat.jsonl").write_text('{"stale": true}\n')
    (matched / "stale-flat.jsonl").write_text('{"stale": true}\n')
    (loop_unmatched / "stale-flat.jsonl").write_text('{"stale": true}\n')
    result = _run_match(corpus_dir, unmatched, matched, loop_unmatched)
    assert result.returncode == 0, result.stderr
    assert not (unmatched / "stale-flat.jsonl").exists()
    assert not (matched / "stale-flat.jsonl").exists()
    assert not (loop_unmatched / "stale-flat.jsonl").exists()
    assert (unmatched / "o" / "r" / "pr-1.jsonl").exists()


def test_guard_failure_preserves_existing_outputs(tmp_path):
    """Clear must happen AFTER the guard. A mixed-layout corpus trips the guard;
    pre-existing matched/+unmatched/ outputs must survive (not be wiped)."""
    corpus_dir = tmp_path / "corpus"
    _write_nested(corpus_dir, "o", "r", 1)
    (corpus_dir / "pr-99.json").write_text("{}")  # trips the mixed guard
    unmatched = tmp_path / "unmatched"
    matched = tmp_path / "matched"
    unmatched.mkdir()
    matched.mkdir()
    loop_unmatched = tmp_path / "loop_unmatched"
    loop_unmatched.mkdir()
    (unmatched / "keep.jsonl").write_text('{"keep": true}\n')
    (matched / "keep.jsonl").write_text('{"keep": true}\n')
    (loop_unmatched / "keep.jsonl").write_text('{"keep": true}\n')
    result = _run_match(corpus_dir, unmatched, matched, loop_unmatched)
    assert result.returncode != 0
    assert (unmatched / "keep.jsonl").exists()
    assert (loop_unmatched / "keep.jsonl").exists()
    assert (matched / "keep.jsonl").exists()
