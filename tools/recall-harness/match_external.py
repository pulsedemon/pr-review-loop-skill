#!/usr/bin/env python3
"""A2: Match external findings against loop findings using scripts/match_findings.py.

For each corpus file in --corpus-dir:
- Skip external findings without file/line (unanchored: the matcher requires
  both; unanchored go directly to A4's unanchored buckets).
- For each anchored external finding, apply scripts/match_findings.py's
  `is_match` in-process against every anchored loop finding, scoring
  token_containment at CONTAINMENT_THRESHOLD within HARNESS_LINE_WINDOW rather
  than the loop's own jaccard defaults (see the README on why). If any match,
  bucket as `matched`; else `unmatched`.
- Write matched/<owner>/<repo>/pr-<N>.jsonl (full pair: external + matched_loop) and
  unmatched/<owner>/<repo>/pr-<N>.jsonl (external only).

Each output line is one JSON object with stable keys: finding_id (recomputed
from the external finding using the same hash as A1's collect_pr_corpus),
external, and matched_loop (matched only).

the matcher module is imported once via --match-script (default
scripts/match_findings.py). missing or wrongly typed fields raise RuntimeError
so malformed inputs cannot inflate the candidate-miss bucket.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import (  # noqa: E402
    finding_id,
    require_corpus_version,
    require_nested_layout,
)
from collect_pr_corpus import (  # type: ignore[import-not-found]  # noqa: E402
    CORPUS_VERSION,
    matched_filename,
)

# Back-compat alias: external callers and tests imported finding_id_for from
# this module before the _shared extraction. Keep the alias so we don't break
# them in a fix-batch PR.
finding_id_for = finding_id

_HARNESS_DIR = Path(__file__).resolve().parent
DEFAULT_CORPUS_DIR = _HARNESS_DIR / "corpus"
DEFAULT_UNMATCHED_DIR = _HARNESS_DIR / "unmatched"
DEFAULT_MATCHED_DIR = _HARNESS_DIR / "matched"
DEFAULT_LOOP_UNMATCHED_DIR = _HARNESS_DIR / "loop_unmatched"
DEFAULT_MATCH_SCRIPT = _HARNESS_DIR.parents[1] / "scripts" / "match_findings.py"

# allow external reviewers to anchor the same issue to different lines.
# this window is independent of the loop's finding-deduplication window.
HARNESS_LINE_WINDOW = 15


def _scorer_stamp(matcher: ModuleType) -> str:
    """stamp the scoring contract; record counts cannot detect stale scoring rules."""
    return f"token_containment@{matcher.CONTAINMENT_THRESHOLD:g}/win{HARNESS_LINE_WINDOW}"


def _is_anchored(finding: dict) -> bool:
    return finding.get("file") is not None and finding.get("line") is not None


def _load_matcher(match_script: Path) -> ModuleType:
    """Import match_findings.py once per run so its rules apply in-process."""
    spec = importlib.util.spec_from_file_location("match_findings", match_script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load matcher module from {match_script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in (
        "token_overlap",
        "token_containment",
        "is_match",
        "tokens",
        "LINE_WINDOW",
        "OVERLAP_THRESHOLD",
        "CONTAINMENT_THRESHOLD",
        "MIN_CONTAINMENT_TOKENS",
    ):
        if not hasattr(module, name):
            raise RuntimeError(f"matcher at {match_script} is missing {name}")
    return module


def _run_matcher(matcher: ModuleType, a: dict, b: dict) -> bool:
    """return whether a and b match under the harness's containment scorer.

    containment accommodates the length difference between loop findings and
    bot comments. malformed inputs raise RuntimeError so validation failures
    cannot inflate the candidate-miss bucket.
    """
    for label, obj in (("a", a), ("b", b)):
        for key, typ in (("file", str), ("line", int), ("summary", str)):
            if key not in obj:
                raise RuntimeError(
                    f"matcher input {label}: missing required field '{key}' on "
                    f"{a.get('file')}:{a.get('line')} vs {b.get('file')}:{b.get('line')}"
                )
            value = obj[key]
            if not isinstance(value, typ) or (typ is int and isinstance(value, bool)):
                raise RuntimeError(
                    f"matcher input {label}: field '{key}' has wrong type on "
                    f"{a.get('file')}:{a.get('line')} vs {b.get('file')}:{b.get('line')}"
                )
    return matcher.is_match(
        a,
        b,
        scorer=matcher.token_containment,
        threshold=matcher.CONTAINMENT_THRESHOLD,
        line_window=HARNESS_LINE_WINDOW,
    )


def _best_near_miss(
    matcher: ModuleType, ext_for_matcher: dict, anchored_loop: list[dict]
) -> tuple[float | None, str | None, int | None]:
    """Return (best_overlap_score, best_loop_summary, line_delta) over same-file
    loop findings.

    `ext_for_matcher` is the same trimmed `{file, line, summary}` dict that
    `_run_matcher` validates at match_external.py:100-128 (all three keys
    present, correct types). Do not pass a raw external: `ext["summary"]`
    and `ext["line"]` below are unchecked accesses, by design, because the
    caller is responsible for trimming. Passing a raw external will KeyError
    silently at runtime, not at test time.

    Scores containment, the same scorer `_run_matcher` gates on, so a near-miss
    number is directly comparable to the threshold it fell short of.

    Scope is restricted to same-file findings (mirroring the matcher's first
    short-circuit at match_findings.py:135) because that's the cohort the
    matcher would have considered. Line-window is *not* applied: the whole
    point of the near-miss diagnostic is to see whether the matcher's
    summary-overlap rule is the gate that fired; restricting by line again
    would hide the signal. `line_delta` is recorded so the reader can
    distinguish a high score within ±HARNESS_LINE_WINDOW (genuine near-miss) from a
    high score 200 lines away (summary-similar prose elsewhere in the file,
    *not* the same finding the bot reviewer raised). Returns
    (None, None, None) if no same-file loop finding exists, or if none of them
    clears MIN_CONTAINMENT_TOKENS: an unscorable pair is not a zero score.
    """
    same_file = [f for f in anchored_loop if f.get("file") == ext_for_matcher["file"]]
    if not same_file:
        return None, None, None
    # token_containment returns 0.0 both for genuine zero overlap and for a pair
    # it cannot judge because one side is under MIN_CONTAINMENT_TOKENS. Only the
    # first is a measurement. Serializing the second as 0.0 would put an
    # unscorable row into report.py's decision-rule denominator as below-cut
    # evidence, diluting the statistic with pairs nothing scored.
    scorable = [
        f
        for f in same_file
        if len(matcher.tokens(ext_for_matcher["summary"])) >= matcher.MIN_CONTAINMENT_TOKENS
        and len(matcher.tokens(f["summary"])) >= matcher.MIN_CONTAINMENT_TOKENS
    ]
    if not scorable:
        return None, None, None
    best_score = -1.0
    best_summary: str | None = None
    best_line: int | None = None
    for f in scorable:
        score = matcher.token_containment(ext_for_matcher["summary"], f["summary"])
        if score > best_score:
            best_score = score
            best_summary = f.get("summary")
            best_line = f.get("line")
    line_delta = abs(ext_for_matcher["line"] - best_line) if best_line is not None else None
    return best_score, best_summary, line_delta


def process_corpus_file(
    corpus_path: Path,
    unmatched_dir: Path,
    matched_dir: Path,
    loop_unmatched_dir: Path,
    matcher: ModuleType,
) -> None:
    corpus = json.loads(corpus_path.read_text())
    require_corpus_version(corpus, corpus_path, CORPUS_VERSION)
    if corpus.get("skipped"):
        return
    if corpus.get("is_open"):
        # In-flight PRs are surfaced separately by A4 (report.py); skip A2 so we
        # don't leave stale matched/unmatched JSONL behind once they merge.
        return
    pr = corpus["pr"]
    owner = corpus["owner"]
    repo = corpus["repo"]
    loop = corpus.get("loop_findings", [])
    external = corpus.get("external_findings", [])

    matched_lines: list[str] = []
    unmatched_lines: list[str] = []

    anchored_loop = [f for f in loop if _is_anchored(f)]
    # Which loop findings some external corroborated. Tracked by index because
    # loop findings are plain dicts (unhashable) and carry no id of their own.
    corroborated_loop_idx: set[int] = set()

    for ext in external:
        if not _is_anchored(ext):
            continue  # Unanchored externals never feed the matcher.
        ext_for_matcher = {
            "file": ext["file"],
            "line": ext["line"],
            "summary": ext["summary"],
        }
        matched_loop = None
        for idx, loop_f in enumerate(anchored_loop):
            if _run_matcher(matcher, ext_for_matcher, loop_f):
                matched_loop = loop_f
                corroborated_loop_idx.add(idx)
                break
        record = {
            "finding_id": finding_id_for(ext),
            "external": ext,
            "scorer": _scorer_stamp(matcher),
        }
        if matched_loop is not None:
            record["matched_loop"] = matched_loop
            matched_lines.append(json.dumps(record, sort_keys=True))
        else:
            score, summary, line_delta = _best_near_miss(matcher, ext_for_matcher, anchored_loop)
            record["best_near_miss_score"] = score
            record["best_near_miss_loop_summary"] = summary
            record["best_near_miss_line_delta"] = line_delta
            unmatched_lines.append(json.dumps(record, sort_keys=True))

    # Anchored loop findings no external corroborated. Feeds the precision bucket:
    # non-corroboration is NOT evidence of a false positive (the external reviewer
    # has its own recall problem), so these are labeled by hand against the diff.
    loop_unmatched_lines = [
        json.dumps(
            {
                "finding_id": finding_id(loop_f),
                "loop_finding": loop_f,
                "scorer": _scorer_stamp(matcher),
            },
            sort_keys=True,
        )
        for idx, loop_f in enumerate(anchored_loop)
        if idx not in corroborated_loop_idx
    ]

    out_name = matched_filename(owner, repo, pr)
    unmatched_out = unmatched_dir / out_name
    matched_out = matched_dir / out_name
    loop_unmatched_out = loop_unmatched_dir / out_name
    unmatched_out.parent.mkdir(parents=True, exist_ok=True)
    matched_out.parent.mkdir(parents=True, exist_ok=True)
    loop_unmatched_out.parent.mkdir(parents=True, exist_ok=True)
    unmatched_out.write_text("\n".join(unmatched_lines) + ("\n" if unmatched_lines else ""))
    matched_out.write_text("\n".join(matched_lines) + ("\n" if matched_lines else ""))
    loop_unmatched_out.write_text(
        "\n".join(loop_unmatched_lines) + ("\n" if loop_unmatched_lines else "")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="A2: match external findings")
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument(
        "--unmatched-dir",
        type=Path,
        default=DEFAULT_UNMATCHED_DIR,
    )
    parser.add_argument("--matched-dir", type=Path, default=DEFAULT_MATCHED_DIR)
    parser.add_argument(
        "--loop-unmatched-dir",
        type=Path,
        default=DEFAULT_LOOP_UNMATCHED_DIR,
    )
    parser.add_argument(
        "--match-script",
        type=Path,
        default=DEFAULT_MATCH_SCRIPT,
    )
    args = parser.parse_args()

    if not args.corpus_dir.is_dir():
        print(f"match_external: corpus dir {args.corpus_dir} not found", file=sys.stderr)
        return 1

    matcher = _load_matcher(args.match_script)
    corpora = sorted(args.corpus_dir.glob("*/*/pr-*.json"))
    require_nested_layout(args.corpus_dir, corpora, CORPUS_VERSION)
    # Derived outputs are 100% a function of the corpus; rebuild from scratch so
    # neither stale flat leftovers nor stale nested files (PRs since removed from
    # the corpus) can persist. Runs only after the layout guard passes, so a
    # guard failure never destroys prior good outputs.
    for derived in (args.unmatched_dir, args.matched_dir, args.loop_unmatched_dir):
        if derived.is_dir():
            shutil.rmtree(derived)
        derived.mkdir(parents=True, exist_ok=True)
    for corpus_path in corpora:
        process_corpus_file(
            corpus_path,
            args.unmatched_dir,
            args.matched_dir,
            args.loop_unmatched_dir,
            matcher,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
