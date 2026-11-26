#!/usr/bin/env python3
"""A4: Render REPORT.md from corpus, matched/unmatched JSONL, and labels.csv.

The matched JSONL on disk is the full set written by A2; A4 deterministically
samples a subset (rate * len, with a configurable minimum) for the matcher-quality
spot-check; labels for that sample are read from labels.csv (populated manually
per the workflow in tools/recall-harness/README.md). Sampling is by sorted
finding_id, so re-runs sample identically.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import NamedTuple

from _shared import (
    DEFAULT_CORPUS_DIR,
    DEFAULT_LOOP_UNMATCHED_DIR,
    DEFAULT_MATCHED_DIR,
    DEFAULT_UNMATCHED_DIR,
    HARNESS_DIR,
    finding_id,
    is_anchored,
    require_corpus_identity,
    require_corpus_version,
    require_nested_layout,
)
from collect_pr_corpus import (
    CORPUS_VERSION,
    matched_filename,
)

DEFAULT_LABELS = HARNESS_DIR / "labels.csv"

MATCHED_FALSE_WARN_THRESHOLD = 0.10
NEAR_MISS_DECISION_CUT = 0.45
NEAR_MISS_DECISION_SHARE = 0.30

# keep the on-disk scorer contract independent of matcher execution; the
# threshold and window determine how this report interprets stored scores.
EXPECTED_SCORER = "token_containment@0.5/win15"


class NearMissRow(NamedTuple):
    owner: str
    repo: str
    pr: int
    score: float
    line_delta: int | None
    ext_summary: str
    loop_summary: str
    is_real_miss: bool


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    _require_scorer(rows, path)
    return rows


def _require_scorer(rows: list[dict], path: Path) -> None:
    """counts can agree even when different scoring rules change which findings match."""
    for row in rows:
        scorer = row.get("scorer")
        if scorer != EXPECTED_SCORER:
            raise SystemExit(
                f"{path}: record scored by {scorer!r}, expected {EXPECTED_SCORER!r}. "
                "Re-run A2 (match_external.py) before A4: these scores are on a "
                "different scale than this report interprets."
            )


_REQUIRED_LABEL_COLUMNS = ("owner", "repo", "pr", "bucket", "finding_id", "label")

# Bucket -> labels valid in it, mirroring label.md. Bucket and label are join keys
# read at hard-coded call sites below, so an unrecognized value is not a loud
# error but a silent omission: the row reads as labeled work while contributing to
# nothing. That matters most for the precision denominator, where a dropped row
# shifts a published percentage rather than just a count.
_BUCKET_LABELS: dict[str, frozenset[str]] = {
    "unmatched": frozenset({"real_miss", "noise", "out_of_scope", "unrecoverable"}),
    "matched_sample": frozenset({"matched_true", "matched_false"}),
    "unanchored_external": frozenset(
        {"unanchored_real_miss", "unanchored_noise", "unanchored_out_of_scope"}
    ),
    "unanchored_loop": frozenset({"unanchored_loop_keep", "unanchored_loop_drop"}),
    "loop_unmatched": frozenset(
        {
            "loop_true_positive",
            "loop_false_positive",
            "loop_low_value",
            "loop_unjudgeable",
        }
    ),
}


def _load_labels(
    path: Path,
) -> dict[tuple[str, str, str, str, str], tuple[str, str]]:
    """return {(owner, repo, pr, bucket, finding_id): (label, notes)}.

    owner,repo,pr,bucket,finding_id,label columns are required; notes is optional.
    validate the header before reading rows so an empty malformed file fails.
    """
    if not path.exists():
        return {}
    out: dict[tuple[str, str, str, str, str], tuple[str, str]] = {}
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or ()
        for col in _REQUIRED_LABEL_COLUMNS:
            if col not in fieldnames:
                raise RuntimeError(
                    f"labels.csv missing required column '{col}': schema "
                    "is owner,repo,pr,bucket,finding_id,label,notes"
                )
        for row in reader:
            bucket, label = row["bucket"], row["label"]
            valid = _BUCKET_LABELS.get(bucket)
            if valid is None:
                raise RuntimeError(
                    f"labels.csv: unknown bucket {bucket!r}: expected one of "
                    f"{', '.join(sorted(_BUCKET_LABELS))}"
                )
            # An empty label is a deliberate "not judged yet" row, not a typo.
            if label and label not in valid:
                raise RuntimeError(
                    f"labels.csv: label {label!r} is not valid for bucket {bucket!r}: "
                    f"expected one of {', '.join(sorted(valid))}"
                )
            key = (row["owner"], row["repo"], row["pr"], bucket, row["finding_id"])
            out[key] = (label, row.get("notes", ""))
    return out


def _sample_matched(pr_matched: list[dict], rate: float, minimum: int) -> list[dict]:
    """Deterministic sample: ceil(rate * len) or `minimum`, whichever is larger.

    Selection by sorted finding_id so re-runs produce identical samples."""
    target = max(int(math.ceil(rate * len(pr_matched))), minimum)
    sorted_matches = sorted(pr_matched, key=lambda r: r.get("finding_id", ""))
    return sorted_matches[: min(target, len(sorted_matches))]


_WORD_RE = re.compile(r"\b\w+\b")


def _candidate_cause(summary: str) -> str:
    """Cheap keyword-based grouping. Refine after first labeling round.

    Uses word-boundary tokenization rather than substring containment so
    'latest' doesn't classify under 'test' and 'failure' doesn't catch every
    'fail-' prefix. Multi-word keys (e.g. 'shared state') still match via
    phrase containment on the lowercased summary; single-word keys use the
    tokenized set."""
    s = summary.lower()
    tokens = set(_WORD_RE.findall(s))

    def _hit(keys: tuple[str, ...]) -> bool:
        for k in keys:
            # `\b\w+\b` splits hyphens, so "hard-coded" is never a single token.
            # Match any key carrying a separator by containment, as for phrases.
            if " " in k or "-" in k:
                if k in s:
                    return True
            elif k in tokens:
                return True
        return False

    if _hit(("timeout", "retry", "fallback", "env var", "config", "feature flag")):
        return "config / env coupling (would be caught by blind_spots persona)"
    if _hit(("async", "await", "race", "concurrency", "shared state", "mutex", "lock")):
        return "concurrency / ordering (would be caught by blind_spots persona)"
    # security keys precede generic correctness keys so "auth bypass" stays security.
    if _hit(
        (
            "auth",
            "authentication",
            "authorization",
            "unauthenticated",
            "unauthorized",
            "secret",
            "credential",
            "injection",
            "xss",
            "csrf",
        )
    ):
        return "security (would be caught by sharpening security persona)"
    # generic failure wording belongs to correctness unless the subject is a schema.
    # phrase matches avoid treating identifiers such as EXPECTED_SCHEMA_ID_PREFIX
    # as schema claims.
    schema_subject = _hit(("schema is too", "schema too", "schema allows", "schema accepts"))
    if not schema_subject and _hit(
        (
            "attributeerror",
            "unicodedecodeerror",
            "uncaught",
            "can return none",
            "return none",
            "non-mapping type",
            "hard-coded",
            "hardcoded",
            "unguarded",
            "edge case",
            "too loose",
            "too permissive",
            "bypass",
            "treated as",
            "without first checking",
            "without specifying",
            "without catching",
            "only checks that",
            "no consistency check",
            "ambiguous across",
            "inherit",
            "assumes",
        )
    ):
        return "correctness (would be caught by sharpening correctness persona)"
    # Must precede the error-path branch: summaries like "schema fails to
    # validate" carry both type_design and error-path tokens; type_design wins.
    # "schema" is phrase-restricted rather than a bare token because on its own
    # it claimed correctness findings that merely mentioned a schema constant.
    if _hit(
        (
            "invariant",
            "type signature",
            "type contract",
            "type design",
            "additional properties",
            "additionalproperties",
            "required list",
            "required field",
            "required fields",
            "object form",
            "schema accepts",
            "schema is too",
            "schema too",
            "schema allows",
            "schema doesn't",
            "schema does not",
            "schema fails",
            "enforce schema",
            "enforce required",
            "enforce additional",
            "mutual exclusion",
            "mutually exclusive",
        )
    ):
        return "type design (would be caught by sharpening type_design persona)"
    if _hit(("error", "exception", "catch", "throw", "raise", "fail")):
        return "error-path coverage (would be caught by blind_spots persona)"
    if _hit(("test", "assertion", "asserts", "expect", "coverage")):
        return "test coverage (would be caught by sharpening Move A or B on tests persona)"
    return "unrecoverable or uncategorized"


def main() -> int:
    parser = argparse.ArgumentParser(description="A4: render REPORT.md")
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
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--sample-rate", type=float, default=0.10)
    parser.add_argument("--sample-min", type=int, default=3)
    args = parser.parse_args()

    corpora = sorted(args.corpus_dir.glob("*/*/pr-*.json")) if args.corpus_dir.is_dir() else []
    require_nested_layout(args.corpus_dir, corpora, CORPUS_VERSION)
    labels = _load_labels(args.labels)

    out = io.StringIO()
    out.write("# Recall harness report\n\n")
    out.write(f"PRs analyzed: {len(corpora)}\n\n")

    total_external = 0
    total_anchored_external = 0
    total_matched = 0
    total_unmatched = 0
    total_unanchored_external = 0
    total_unanchored_loop = 0
    # matched summaries establish overlap, not independent discovery or usefulness.
    # uncorroborated findings require manual judgments.
    precision_counts: Counter = Counter()

    sampled_prs = total_sample = total_judged_sample = total_false = 0
    # `miss_groups` keys candidate-cause to list of (owner, repo, pr, summary).
    miss_groups: dict[str, list[tuple[str, str, int, str]]] = defaultdict(list)
    label_distribution: Counter = Counter()
    # PRs where corroborated + loop_unmatched != the corpus's anchored loop count.
    loop_invariant_violations: list[tuple[str, str, int, int, int, int]] = []
    # PRs where matched/<...>.jsonl + unmatched/<...>.jsonl total doesn't equal
    # the anchored external count from the corpus file. Almost always means A2
    # wasn't re-run after A1 regenerated the corpus, so the report's bucket
    # counts are stale relative to the source.
    # Tuple shape: (owner, repo, pr, anchored_external, matched, unmatched).
    invariant_violations: list[tuple[str, str, int, int, int, int]] = []
    # Filtered to score not None: null-score rows have no same-file loop
    # finding and so carry no diagnostic signal.
    near_miss_rows: list[NearMissRow] = []
    # Per-repo totals for the "## By owner/repo" section.
    repo_totals: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"prs": 0, "matched": 0, "unmatched": 0}
    )
    # In-flight PRs (collected with --include-open) are reported separately so
    # they don't pollute totals or per-repo aggregates with non-reproducible
    # head-of-branch state.
    in_flight: list[tuple[str, str, int]] = []

    for corpus_path in corpora:
        corpus = json.loads(corpus_path.read_text())
        require_corpus_version(corpus, corpus_path, CORPUS_VERSION)
        require_corpus_identity(corpus, corpus_path)
        if corpus.get("skipped"):
            continue
        pr = corpus["pr"]
        owner = corpus["owner"]
        repo = corpus["repo"]
        if corpus.get("is_open"):
            in_flight.append((owner, repo, pr))
            continue
        externals = corpus.get("external_findings", [])
        total_external += len(externals)
        anchored_externals = sum(1 for e in externals if is_anchored(e))
        total_anchored_external += anchored_externals
        unanchored_externals = len(externals) - anchored_externals
        total_unanchored_external += unanchored_externals
        total_unanchored_loop += len(corpus.get("loop_findings_unanchored", []))

        jsonl_name = matched_filename(owner, repo, pr)
        matched = _load_jsonl(args.matched_dir / jsonl_name)
        unmatched = _load_jsonl(args.unmatched_dir / jsonl_name)
        total_matched += len(matched)

        # One matched row per EXTERNAL finding, so two comments on the same loop
        # finding yield two rows. Precision is defined over loop findings, so
        # dedupe before counting or both numerator and population inflate.
        #
        # A pair a labeler marked `matched_false` should not have been made, so
        # its loop side was never corroborated and cannot be credited as a catch.
        # Only labeled-false pairs drop: `matched_sample` is a spot-check, so an
        # unlabeled pair is unjudged rather than known-good.
        def _loop_key(m):
            ml = m.get("matched_loop") or {}
            return (ml.get("file"), ml.get("line"), ml.get("summary"))

        # Structural: what A2 actually paired, used by the pipeline invariant.
        paired_loop = {_loop_key(m) for m in matched}
        # Scored: excludes pairs a labeler rejected. Kept separate from
        # `paired_loop` so a labeling act never reads as stale A2 output.
        corroborated_loop = {
            _loop_key(m)
            for m in matched
            if labels.get(
                (owner, repo, str(pr), "matched_sample", m.get("finding_id", "")),
                ("", ""),
            )[0]
            != "matched_false"
        }
        precision_counts["corroborated"] += len(corroborated_loop)
        loop_unmatched_records = _load_jsonl(args.loop_unmatched_dir / jsonl_name)
        uncorroborated_ids = [lu.get("finding_id", "") for lu in loop_unmatched_records]
        rejected_loop = {
            _loop_key(m): m.get("matched_loop") or {}
            for m in matched
            if _loop_key(m) not in corroborated_loop
        }
        for loop_finding in rejected_loop.values():
            rejected_id = finding_id(loop_finding)
            if rejected_id not in uncorroborated_ids:
                uncorroborated_ids.append(rejected_id)
        for loop_id in uncorroborated_ids:
            label, _ = labels.get(
                (owner, repo, str(pr), "loop_unmatched", loop_id),
                ("", ""),
            )
            label_distribution[("loop_unmatched", label or "unlabeled")] += 1
            precision_counts[label or "unlabeled"] += 1
        total_unmatched += len(unmatched)

        repo_totals[(owner, repo)]["prs"] += 1
        repo_totals[(owner, repo)]["matched"] += len(matched)
        repo_totals[(owner, repo)]["unmatched"] += len(unmatched)

        # Invariant: every anchored external from corpus must land in
        # matched/ or unmatched/. A2 is what populates those, so a mismatch
        # means the two halves of the pipeline disagree (typically: A1 ran,
        # A2 didn't).
        if len(matched) + len(unmatched) != anchored_externals:
            invariant_violations.append(
                (owner, repo, pr, anchored_externals, len(matched), len(unmatched))
            )

        # Loop-side mirror. _load_jsonl reads a missing file as an empty bucket,
        # so without this a pre-loop_unmatched A2 run would publish precision
        # over the matched rows alone with every uncorroborated finding absent.
        anchored_loop = sum(1 for f in corpus.get("loop_findings", []) if is_anchored(f))
        if len(paired_loop) + len(loop_unmatched_records) != anchored_loop:
            loop_invariant_violations.append(
                (
                    owner,
                    repo,
                    pr,
                    anchored_loop,
                    len(paired_loop),
                    len(loop_unmatched_records),
                )
            )

        # Matcher quality spot-check sample (deterministic).
        sample = _sample_matched(matched, args.sample_rate, args.sample_min)
        sampled_prs += 1
        total_sample += len(sample)
        for s in sample:
            label, _ = labels.get(
                (owner, repo, str(pr), "matched_sample", s.get("finding_id", "")),
                ("", ""),
            )
            label_distribution[("matched_sample", label or "unlabeled")] += 1
            if label in ("matched_true", "matched_false"):
                total_judged_sample += 1
            if label == "matched_false":
                total_false += 1

        # Group misses by candidate cause.
        for u in unmatched:
            label, _ = labels.get(
                (owner, repo, str(pr), "unmatched", u.get("finding_id", "")),
                ("", ""),
            )
            label_distribution[("unmatched", label or "unlabeled")] += 1
            # Capture for ALL unmatched records, not just real_miss. The capture
            # runs after label_distribution is tallied so the label histogram
            # stays accurate, and before the real_miss filter so unlabeled or
            # out_of_scope unmatched rows with a same-file loop finding still
            # flow into the diagnostic. Reversing either gate would either drop
            # non-real_miss diagnostics or skew the label distribution.
            score = u.get("best_near_miss_score")
            if score is not None:
                ext_summary = u.get("external", {}).get("summary", "")
                loop_summary = u.get("best_near_miss_loop_summary", "") or ""
                line_delta = u.get("best_near_miss_line_delta")  # may be None on older JSONL
                near_miss_rows.append(
                    NearMissRow(
                        owner=owner,
                        repo=repo,
                        pr=pr,
                        score=float(score),
                        line_delta=line_delta,
                        ext_summary=ext_summary,
                        loop_summary=loop_summary,
                        is_real_miss=(label == "real_miss"),
                    )
                )
            if label != "real_miss":
                continue
            summary = u.get("external", {}).get("summary", "")
            miss_groups[_candidate_cause(summary)].append((owner, repo, pr, summary))

    # the matcher emits no JSONL for unanchored findings, so tally their labels directly.
    for (_o, _r, _pr, bucket, _fid), (label, _notes) in labels.items():
        if bucket in ("unanchored_external", "unanchored_loop") and label:
            label_distribution[(bucket, label)] += 1

    # Pipeline-consistency warning. Emit before Totals so a reader skimming
    # the top of the report can't trust the matched/unmatched numbers without
    # seeing that some of them are stale. Totals include matched + unmatched
    # accumulated from PRs in invariant_violations, so they're misleading on
    # their own without this disclaimer above them.
    if invariant_violations:
        out.write("## PIPELINE WARNING: stale matcher outputs\n\n")
        out.write(
            "For the following PRs, `matched + unmatched != anchored_external`. "
            "Most likely cause: A1 (collect_pr_corpus.py) was re-run but A2 "
            "(match_external.py) wasn't, so matched/ and unmatched/ describe an "
            "older corpus. Re-run A2 before trusting the totals and groupings "
            "below.\n\n"
        )
        for owner, repo, pr, anchored, matched_n, unmatched_n in invariant_violations:
            out.write(
                f"- {owner}/{repo} PR #{pr}: anchored_external={anchored}, "
                f"matched+unmatched={matched_n + unmatched_n} "
                f"(matched={matched_n}, unmatched={unmatched_n})\n"
            )
        out.write("\n")

    if loop_invariant_violations:
        out.write("## PIPELINE WARNING: stale loop-side matcher outputs\n\n")
        out.write(
            "For the following PRs, `corroborated + loop_unmatched != anchored "
            "loop findings`. Same cause as above, and it silently understates the "
            "precision denominator rather than the recall one. Re-run A2 before "
            "trusting the precision figure below.\n\n"
        )
        for owner, repo, pr, anchored, corrob_n, loop_un_n in loop_invariant_violations:
            out.write(
                f"- {owner}/{repo} PR #{pr}: anchored loop findings={anchored}, "
                f"corroborated+loop_unmatched={corrob_n + loop_un_n} "
                f"(corroborated={corrob_n}, loop_unmatched={loop_un_n})\n"
            )
        out.write("\n")

    # Totals.
    out.write("## Totals\n\n")
    out.write(
        f"- External findings: {total_external} "
        f"({total_anchored_external} anchored, "
        f"{total_unanchored_external} unanchored)\n"
    )
    out.write(f"- Matched (loop caught): {total_matched}\n")
    out.write(f"- Unmatched (candidate misses): {total_unmatched}\n")
    out.write(f"- Loop unanchored: {total_unanchored_loop}\n\n")

    # Label distribution.
    out.write("## Label distribution\n\n")
    if not label_distribution:
        out.write("_(no labels yet: populate `labels.csv` and re-run)_\n\n")
    else:
        for (bucket, label), count in sorted(label_distribution.items()):
            out.write(f"- {bucket} / {label}: {count}\n")
        out.write("\n")

    # Misses grouped by candidate cause.
    out.write("## Misses by candidate cause (anchored `real_miss` only)\n\n")
    if not miss_groups:
        out.write("_(no real_miss labels yet)_\n\n")
    else:
        for cause, items in sorted(miss_groups.items(), key=lambda kv: -len(kv[1])):
            out.write(f"### {cause} ({len(items)} miss{'es' if len(items) != 1 else ''})\n\n")
            for owner, repo, pr, summary in items:
                out.write(f"- {owner}/{repo} PR #{pr}: {summary}\n")
            out.write("\n")

    if near_miss_rows:
        out.write("## Matcher near-misses (unmatched externals with a same-file loop finding)\n\n")
        real_miss_with_score = [r for r in near_miss_rows if r.is_real_miss]
        rm_total = len(real_miss_with_score)
        rm_at_cut = sum(1 for r in real_miss_with_score if r.score >= NEAR_MISS_DECISION_CUT)
        if rm_total:
            pct = 100.0 * rm_at_cut / rm_total
            out.write(
                f"Near-miss diagnostic: {rm_at_cut} of {rm_total} real_miss rows "
                f"have score >= {NEAR_MISS_DECISION_CUT:.2f} ({pct:.1f}%). "
                f"Decision rule: >= {NEAR_MISS_DECISION_SHARE:.0%} => matcher recall is "
                "meaningfully limiting.\n\n"
            )
        else:
            # Suppress the "0 of 0 (0.0%)" rendering when no unmatched record
            # with a same-file loop finding has been labeled real_miss yet:
            # printing "0 of 0 ... => matcher recall is meaningfully limiting"
            # reads as a falsified verdict on an unlabeled corpus.
            out.write(
                "Near-miss diagnostic: no real_miss labels on rows with a same-file "
                "loop finding yet: decision-rule statistic is not computable.\n\n"
            )
        # the final upper bound includes scores of exactly one in half-open bins.
        if rm_total:
            edges = sorted({0.00, 0.10, 0.20, 0.30, 0.40, NEAR_MISS_DECISION_CUT, 0.50, 0.75, 1.01})
            bins = list(pairwise(edges))
            counts = [sum(1 for r in real_miss_with_score if lo <= r.score < hi) for lo, hi in bins]
            out.write(f"Real_miss near-miss score distribution (n={rm_total}):\n")
            for (lo, hi), c in zip(bins, counts, strict=True):
                out.write(f"  [{lo:.2f}-{hi:.2f}): {c}\n")
            out.write(
                "Histogram is the source of truth if the "
                f"{NEAR_MISS_DECISION_SHARE:.0%}/{NEAR_MISS_DECISION_CUT:.2f} statistic looks "
                "borderline: both thresholds are starting points.\n\n"
            )
        # keep labeled misses visible above the display limit.
        near_miss_rows.sort(key=lambda r: (-int(r.is_real_miss), -r.score))
        for r in near_miss_rows[:25]:
            tag = " [real_miss]" if r.is_real_miss else ""
            # line_delta_str surfaces when summary similarity is high but the same-file
            # loop finding is spatially far from the external: a high score with
            # delta>HARNESS_LINE_WINDOW is summary-similar prose, not the same finding.
            line_delta_str = f" line_delta={r.line_delta}" if r.line_delta is not None else ""
            out.write(
                f"- {r.owner}/{r.repo} PR #{r.pr} score={r.score:.2f}{line_delta_str}{tag}: "
                f"external: {r.ext_summary[:200]} | loop: {r.loop_summary[:200]}\n"
            )
        out.write("\n")

    # Per-repo breakdown.
    out.write("## By owner/repo\n\n")
    if not repo_totals:
        out.write("_(no corpora yet)_\n\n")
    else:
        for (owner, repo), totals in sorted(repo_totals.items()):
            out.write(
                f"- {owner}/{repo}: {totals['prs']} PR(s), "
                f"matched={totals['matched']}, unmatched={totals['unmatched']}\n"
            )
        out.write("\n")

    # In-flight (open) PRs collected with --include-open. Excluded from totals
    # because their head-of-branch state isn't reproducible: re-running A1
    # later produces a different record for the same PR number.
    if in_flight:
        out.write("## In-flight PRs (excluded from totals)\n\n")
        for owner, repo, pr in in_flight:
            out.write(f"- {owner}/{repo} PR #{pr}\n")
        out.write("\n")

    # Unanchored subsection.
    out.write("## Unanchored findings\n\n")
    out.write(f"- External unanchored: {total_unanchored_external}\n")
    out.write(f"- Loop unanchored: {total_unanchored_loop}\n\n")

    # Matcher quality.
    out.write("## Matcher quality\n\n")
    out.write(f"Spot-check sample: {total_sample} pairs across {sampled_prs} PRs\n")
    out.write(f"Judged sampled pairs: {total_judged_sample}/{total_sample}\n")
    if not total_judged_sample:
        # Same reason the near-miss diagnostic suppresses its 0-of-0 rendering:
        # "0.0%" off an empty denominator reads as a measured pass when nothing
        # was measured, and an empty sample can neither pass nor warn.
        out.write("matched_false rate: n/a, no sampled pairs judged; matcher quality unmeasured\n")
    else:
        rate = total_false / total_judged_sample
        if rate > MATCHED_FALSE_WARN_THRESHOLD:
            out.write(f"matched_false rate: {rate:.1%}\n\n")
            out.write(
                f"**MATCHER QUALITY WARNING**: matched_false rate {rate:.1%} is above "
                f"{MATCHED_FALSE_WARN_THRESHOLD:.0%}. "
                "Tune `scripts/finding_matcher.py` before trusting unmatched-driven groups.\n"
            )
        else:
            out.write(f"matched_false rate: {rate:.1%}\n")

    out.write("\n## Panel precision\n\n")
    judged = (
        precision_counts["corroborated"]
        + precision_counts["loop_true_positive"]
        + precision_counts["loop_false_positive"]
        + precision_counts["loop_low_value"]
    )
    correct = (
        precision_counts["corroborated"]
        + precision_counts["loop_true_positive"]
        + precision_counts["loop_low_value"]
    )
    if judged:
        # loop_low_value counts as correct: factually right but not worth raising
        # is a severity-bar problem, not a wrong claim. It stays a separate label
        # so the two failure modes don't get one number.
        population = judged + precision_counts["loop_unjudgeable"] + precision_counts["unlabeled"]
        out.write(f"Precision: {correct / judged:.1%} ({correct}/{judged})\n\n")
        # Without the coverage line a high percentage over a handful of judged
        # findings reads as a property of the panel rather than of the sample.
        out.write(
            f"Judged {judged / population:.1%} of {population} loop finding(s); "
            "read the rate as a property of that sample.\n\n"
        )
        out.write(f"- corroborated by an external reviewer: {precision_counts['corroborated']}\n")
        for label in ("loop_true_positive", "loop_low_value", "loop_false_positive"):
            out.write(f"- {label}: {precision_counts[label]}\n")
    else:
        out.write("Precision: n/a: no loop findings judged yet\n\n")
    excluded = precision_counts["loop_unjudgeable"]
    unlabeled = precision_counts["unlabeled"]
    if excluded:
        out.write(f"- loop_unjudgeable (excluded from the denominator): {excluded}\n")
    if unlabeled:
        out.write(f"- {unlabeled} loop finding(s) unlabeled, excluded from the denominator\n")
    out.write(
        "\nNever computed from the matched/unmatched split: a loop finding nobody "
        "commented on is not evidence of a false positive.\n"
    )

    out.write("\n## Panel usefulness\n\n")
    manual_judged = judged - precision_counts["corroborated"]
    useful = precision_counts["loop_true_positive"]
    out.write("Useful rate among manually judged, uncorroborated loop findings: ")
    if manual_judged:
        out.write(f"{useful / manual_judged:.1%} ({useful}/{manual_judged})\n\n")
    else:
        out.write("n/a, no manual judgments\n\n")
    manual_population = manual_judged + excluded + unlabeled
    if manual_population:
        out.write(
            f"Manual judgment coverage: {manual_judged / manual_population:.1%} "
            f"({manual_judged}/{manual_population})\n"
        )
    else:
        out.write("Manual judgment coverage: n/a, no uncorroborated loop findings\n")

    sys.stdout.write(out.getvalue())
    return 0


if __name__ == "__main__":
    sys.exit(main())
