"""shared paths, finding identity and corpus validation for the recall harness."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
DEFAULT_CORPUS_DIR = HARNESS_DIR / "corpus"
DEFAULT_UNMATCHED_DIR = HARNESS_DIR / "unmatched"
DEFAULT_MATCHED_DIR = HARNESS_DIR / "matched"
DEFAULT_LOOP_UNMATCHED_DIR = HARNESS_DIR / "loop_unmatched"


def require_corpus_version(corpus: dict, corpus_path: Path, expected_version: int) -> None:
    """reject stored corpora using a different format version."""
    version = corpus.get("corpus_version")
    if version != expected_version:
        raise RuntimeError(
            f"{corpus_path}: corpus_version={version!r}, expected "
            f"{expected_version}. Re-run collect_pr_corpus.py to regenerate."
        )


def require_nested_layout(corpus_dir: Path, corpora: list[Path], expected_version: int) -> None:
    """reject legacy files that the nested corpus scan would omit."""
    if not corpus_dir.is_dir():
        return
    stray_flat = list(corpus_dir.glob("pr-*.json"))
    if stray_flat and corpora:
        raise RuntimeError(
            f"{corpus_dir}: mixed corpus layout detected "
            f"({len(stray_flat)} stray flat pr-*.json file(s) at the top level "
            f"alongside the nested <owner>/<repo>/pr-<N>.json tree). "
            f"Clean the stray files and re-run collect_pr_corpus.py."
        )
    if stray_flat and not corpora:
        raise RuntimeError(
            f"{corpus_dir}: legacy flat corpus layout detected "
            f"({len(stray_flat)} pr-*.json file(s) at the top level). "
            f"Re-run collect_pr_corpus.py to regenerate under "
            f"<owner>/<repo>/pr-<N>.json (CORPUS_VERSION={expected_version})."
        )


def canonical_summary(s: str) -> str:
    """Collapse whitespace, strip. Case preserved for readable labels.csv
    output; the matcher lowercases internally."""
    return " ".join(s.split())


def finding_id(finding: dict) -> str:
    """Stable hash over (file, line, source, canonical_summary)."""
    payload = json.dumps(
        {
            "file": finding.get("file"),
            "line": finding.get("line"),
            "source": finding.get("source"),
            "summary": canonical_summary(finding.get("summary", "")),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
