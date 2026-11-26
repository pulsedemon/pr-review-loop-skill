"""Mixed flat+nested corpus must hard-fail (defense-in-depth + the PR #13 ask),
and match_external must rebuild matched/+unmatched/ so stale outputs can't
persist. The flat-ONLY case keeps its existing 'legacy flat corpus layout'
message (covered by test_version_and_schema_guards.py) and is not retested here."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from collect_pr_corpus import (  # type: ignore[import-not-found]
    CORPUS_VERSION,
    corpus_filename,
)
from match_external import _stage_outputs

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


def test_malformed_later_record_preserves_all_matcher_outputs(tmp_path):
    corpus = tmp_path / "corpus"
    _write_nested(corpus, "o", "r", 1)
    _write_nested(corpus, "o", "r", 2)
    path = corpus / "o/r/pr-2.json"
    record = json.loads(path.read_text())
    record["external_findings"] = [{"file": "a", "line": "bad", "summary": "example"}]
    path.write_text(json.dumps(record))
    outputs = [tmp_path / name for name in ("unmatched", "matched", "loop_unmatched")]
    for directory in outputs:
        directory.mkdir()
        (directory / "previous.jsonl").write_text("previous\n")
    result = _run_match(corpus, *outputs)
    assert result.returncode != 0
    assert "o/r PR #2 external_findings[0]" in result.stderr
    for directory in outputs:
        assert list(directory.iterdir()) == [directory / "previous.jsonl"]
        assert (directory / "previous.jsonl").read_text() == "previous\n"


def test_nested_output_directories_publish_all_buckets(tmp_path):
    corpus = tmp_path / "corpus"
    _write_nested(corpus, "o", "r", 1)
    outer = tmp_path / "derived"
    outputs = [outer / "unmatched", outer, outer / "loop_unmatched"]
    result = _run_match(corpus, *outputs)
    assert result.returncode == 0, result.stderr
    assert all((output / "o/r/pr-1.jsonl").is_file() for output in outputs)


def test_loop_validation_preserves_outputs_without_any_external(tmp_path):
    corpus = tmp_path / "corpus"
    _write_nested(corpus, "o", "r", 1)
    path = corpus / "o/r/pr-1.json"
    record = json.loads(path.read_text())
    record.update(
        loop_findings=[{"file": "a", "line": False, "summary": "text"}], external_findings=[]
    )
    path.write_text(json.dumps(record))
    outputs = [tmp_path / name for name in ("unmatched", "matched", "loop_unmatched")]
    result = _run_match(corpus, *outputs)
    assert result.returncode != 0
    assert "loop_findings[0]" in result.stderr
    assert all(not output.exists() for output in outputs)


def test_failed_publication_restores_previous_buckets(tmp_path, monkeypatch):
    outputs = tuple(tmp_path / name for name in ("unmatched", "matched", "loop_unmatched"))
    for output in outputs:
        output.mkdir()
        (output / "previous.jsonl").write_text(output.name)
    rename = Path.rename

    def refuse_second_install(source, target):
        if target == outputs[1] and (source / "next.jsonl").exists():
            raise OSError("cannot install second bucket")
        return rename(source, target)

    monkeypatch.setattr(Path, "rename", refuse_second_install)
    with pytest.raises(OSError, match="cannot install second bucket"):
        with _stage_outputs(outputs, tmp_path / "corpus") as staged:
            for directory in staged:
                (directory / "next.jsonl").write_text("new")
    for output in outputs:
        assert (output / "previous.jsonl").read_text() == output.name
        assert not (output / "next.jsonl").exists()
