#!/usr/bin/env python3
"""Shared finding matcher used by match_findings.py and promote_findings.py."""

import re

LINE_WINDOW = 5
OVERLAP_THRESHOLD = 0.6

# Opt-in scorer for asymmetric-length comparison; see token_containment.
# 0.5 sits mid-margin: on the corpus the weakest true pair scores 0.625 and the
# strongest coincidental one 0.364. At 0.6 the two weakest true pairs are one
# shared token from rejection; at 0.5 they survive that, and the top noise pair
# gaining a token still fails.
CONTAINMENT_THRESHOLD = 0.5
MIN_CONTAINMENT_TOKENS = 8

STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "when",
    }
)

TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokens(summary: str) -> set[str]:
    return {t for t in TOKEN_RE.findall((summary or "").lower()) if t not in STOP_WORDS}


def token_overlap(a: str, b: str) -> float:
    # An empty token set after stop-word filtering carries no signal, so two
    # findings with nothing to compare are not a match.
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def token_containment(a: str, b: str) -> float:
    """Overlap normalized by the smaller token set.

    For summaries of asymmetric length. A terse finding and a verbose one
    describing the same issue score near zero on Jaccard because the union is
    dominated by the longer side: the ceiling is min/max of the two token
    counts however well they agree.

    Returns 0.0 when either side has fewer than `MIN_CONTAINMENT_TOKENS`
    tokens after stop-word filtering, so a short summary trivially contained in
    a long one does not score high on almost no shared evidence. That floor
    means a 0.0 here is "not enough evidence to judge", not "no overlap".

    Not for comparing two loop findings, where the lengths are already
    comparable and a short summary contained in a longer one merges two
    distinct findings. `token_overlap` is correct there and stays the default.
    """
    ta, tb = tokens(a), tokens(b)
    if len(ta) < MIN_CONTAINMENT_TOKENS or len(tb) < MIN_CONTAINMENT_TOKENS:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def is_match(
    a: dict,
    b: dict,
    *,
    scorer=token_overlap,
    threshold: float = OVERLAP_THRESHOLD,
    line_window: int = LINE_WINDOW,
) -> bool:
    """Return whether two finding objects refer to the same issue.

    Match iff: same file AND abs(line_a - line_b) <= `line_window` AND
    `scorer` on the two summaries >= `threshold`.

    The defaults are the §4c rule: <= 5 lines and Jaccard token-overlap on
    lowercased stop-word-filtered summaries >= 0.6. They are keyword-only, so
    a two-argument call is always exactly §4c. Callers comparing populations
    §4c never sees (the recall harness pairs a loop finding against a bot
    comment, which is both longer and written in the opposite register) pass
    their own; see `token_containment`.
    """
    if a.get("file") != b.get("file"):
        return False
    try:
        if abs(int(a["line"]) - int(b["line"])) > line_window:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    return scorer(a.get("summary", ""), b.get("summary", "")) >= threshold


def _located(finding: dict) -> bool:
    # `is not None` rather than truthiness: line 0 and "" are values, not
    # absence, and treating them as absent sends a located finding down the
    # summary-only path where it can match one hundreds of lines away.
    return finding.get("file") is not None and finding.get("line") is not None


def is_match_or_summary(a: dict, b: dict) -> bool:
    """Return whether two findings refer to the same issue, for §4d.

    §4c rejects a missing `line` outright, so a CI blocker carrying `file` and
    no `line` never matches its own repeat and the loop runs to MAX_ITERATIONS
    pushing a commit per iteration. A missing `file` is worse than rejected:
    two absent values compare equal, so unlocated findings would match on fuzzy
    overlap. Hence the gate below, and exact normalized-summary equality
    whenever either side is unlocated.

    Kept separate from is_match so §4c dedupe is unaffected.
    """
    # Gate on location first rather than trying is_match up front: is_match
    # reads two absent `file` values as equal, so two unlocated findings with
    # nearby lines would take the fuzzy-overlap path and match on merely
    # similar summaries, which is the opposite of the exact-equality rule this
    # fallback is supposed to apply.
    if _located(a) and _located(b):
        return is_match(a, b)
    # A file named on both sides still has to agree, or the same summary in two
    # different files would read as one repeated finding. One side omitting it
    # is fine: that is the case this fallback exists for.
    if a.get("file") is not None and b.get("file") is not None and a["file"] != b["file"]:
        return False
    ta, tb = tokens(a.get("summary", "")), tokens(b.get("summary", ""))
    # An empty token set carries no signal, matching token_overlap's choice.
    return bool(ta) and ta == tb
