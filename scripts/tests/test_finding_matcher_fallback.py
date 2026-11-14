"""Unit tests for finding_matcher.is_match_or_summary (the §4d comparison) and
the opt-in containment scorer beside it.

The §4c rule (is_match) is covered by tests/bats/test_match_findings.bats and
must stay unchanged; these cover the §4d fallback and the containment scorer,
including that a default-argument is_match call is still exactly the §4c rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from finding_matcher import (  # noqa: E402
    CONTAINMENT_THRESHOLD,
    OVERLAP_THRESHOLD,
    is_match,
    is_match_or_summary,
    token_containment,
    token_overlap,
)

SUMMARY = "sql injection query built by string concatenation"


def test_unlocated_repeat_matches() -> None:
    # The live bug: identical blockers with no line score 1.0 overlap but
    # is_match returns False, so the loop never sees the repeat.
    a = {"file": "src/db.ts", "summary": SUMMARY}
    b = {"file": "src/db.ts", "summary": SUMMARY}
    assert is_match(a, b) is False
    assert is_match_or_summary(a, b) is True


def test_same_summary_in_different_files_does_not_match() -> None:
    a = {"file": "src/a.ts", "summary": SUMMARY}
    b = {"file": "src/b.ts", "summary": SUMMARY}
    assert is_match_or_summary(a, b) is False


def test_file_present_on_only_one_side_still_matches() -> None:
    # A repeated CI blocker can carry file on one occurrence and omit it on the
    # next; requiring agreement then resurrects the never-matches bug.
    a = {"file": "src/db.ts", "summary": SUMMARY}
    b = {"summary": SUMMARY}
    assert is_match_or_summary(a, b) is True


def test_line_zero_is_a_location_not_an_absence() -> None:
    a = {"file": "src/db.ts", "line": 0, "summary": SUMMARY}
    b = {"file": "src/db.ts", "line": 900, "summary": SUMMARY}
    assert is_match_or_summary(a, b) is False


def test_located_findings_still_defer_to_the_4c_rule() -> None:
    near = {"file": "src/db.ts", "line": 88, "summary": SUMMARY}
    also_near = {"file": "src/db.ts", "line": 89, "summary": SUMMARY}
    far = {"file": "src/db.ts", "line": 900, "summary": SUMMARY}
    assert is_match_or_summary(near, also_near) is True
    assert is_match_or_summary(near, far) is False


def test_unlocated_findings_with_different_summaries_do_not_match() -> None:
    a = {"file": "src/db.ts", "summary": "sql injection in the query builder"}
    b = {"file": "src/db.ts", "summary": "missing null check on the response"}
    assert is_match_or_summary(a, b) is False


@pytest.mark.parametrize("summary", ["", "the a of and is", "   "])
def test_summaries_with_no_signal_do_not_match(summary: str) -> None:
    # Stop-word-only and empty summaries normalize to an empty token set, which
    # would otherwise make every such finding match every other.
    a = {"file": "src/db.ts", "summary": summary}
    b = {"file": "src/db.ts", "summary": summary}
    assert is_match_or_summary(a, b) is False


def test_unlocated_findings_do_not_take_the_fuzzy_path() -> None:
    # is_match reads two absent `file` values as equal, so without gating on
    # location first these would match on 0.6 overlap instead of the exact
    # normalized-summary equality the fallback documents.
    a = {"line": 10, "summary": "sql injection in the query builder"}
    b = {"line": 12, "summary": "sql injection in the query builder path"}
    assert is_match(a, b) is True
    assert is_match_or_summary(a, b) is False


def test_normalization_ignores_case_and_punctuation() -> None:
    a = {"file": "src/db.ts", "summary": "SQL injection: string-built query!"}
    b = {"file": "src/db.ts", "summary": "sql injection, string built query"}
    assert is_match_or_summary(a, b) is True


def test_containment_scores_an_asymmetric_pair_jaccard_cannot_reach() -> None:
    # Verbatim from the corpus: the loop reports what it fixed, the bot reports
    # what is wrong, and the bot writes ~2x more. Jaccard's union denominator
    # caps this at min/max of the token counts however well the two agree.
    loop = "git pull --ff-only relies on upstream tracking instead of explicit origin/$BRANCH"
    bot = (
        "`git pull --ff-only` is invoked without specifying the remote/branch, "
        "so it will pull from whatever upstream the current branch tracks. "
        "Pinning it to `origin/$BRANCH` makes the sync deterministic when a "
        "local branch tracks something else."
    )
    assert token_overlap(loop, bot) < OVERLAP_THRESHOLD
    assert token_containment(loop, bot) >= CONTAINMENT_THRESHOLD


def test_containment_floor_rejects_a_short_summary_swallowed_by_a_longer_one() -> None:
    # Both from one corpus PR, on the same file and line. Two distinct missing
    # tests for two distinct inputs; the shorter is nearly a subset of the
    # longer, so unguarded containment scores 0.857 and §4c would drop one.
    # Jaccard rates them 0.545 and is right to.
    a = "add a regression test asserting exit 2 on `history==[]`."
    b = "add a regression test asserting exit 2 on state.json missing `.iteration`."
    assert token_overlap(a, b) < OVERLAP_THRESHOLD
    assert token_containment(a, b) == 0.0


def test_is_match_without_kwargs_is_the_4c_rule() -> None:
    # The defaults are load-bearing: promote_findings and check_exit_conditions
    # both call positionally, so a changed default silently changes dedupe and
    # NO_PROGRESS. Pin each gate.
    near = {"file": "a.py", "line": 10, "summary": "sql injection in the query builder"}
    same = {"file": "a.py", "line": 12, "summary": "sql injection in the query builder path"}
    assert is_match(near, same) is True
    assert is_match({**near, "file": "b.py"}, same) is False
    assert is_match({**near, "line": 100}, same) is False
    assert is_match(near, {**same, "summary": "unrelated timeout handling"}) is False


def test_is_match_routes_through_the_scorer_it_is_given() -> None:
    # The path the recall harness uses. Without this, is_match could ignore
    # `scorer` or hard-code token_overlap and every other test here would still
    # pass while the harness opt-in silently did nothing.
    loop = {
        "file": "scripts/sync_skill.sh",
        "line": 12,
        "summary": (
            "git pull --ff-only relies on upstream tracking instead of explicit origin/$BRANCH"
        ),
    }
    bot = {
        "file": "scripts/sync_skill.sh",
        "line": 14,
        "summary": (
            "`git pull --ff-only` is invoked without specifying the remote/branch, "
            "so it will pull from whatever upstream the current branch tracks. "
            "Pinning it to `origin/$BRANCH` makes the sync deterministic when a "
            "local branch tracks something else."
        ),
    }
    assert is_match(loop, bot) is False
    assert (
        is_match(
            loop,
            bot,
            scorer=token_containment,
            threshold=CONTAINMENT_THRESHOLD,
        )
        is True
    )


def test_containment_scorer_still_rejects_a_coincidental_pair() -> None:
    # Same file and line, different issues: the loop reports the marker check it
    # added, the bot argues the script should enforce the invariant at all. 0.364
    # containment, so it guards the threshold's lower bound against being lowered
    # far enough to admit co-located prose.
    loop = {
        "file": "scripts/reply_pr_comments.sh",
        "line": 43,
        "summary": (
            "addressed: the script now rejects a body whose first line is not the reply marker."
        ),
    }
    bot = {
        "file": "scripts/reply_pr_comments.sh",
        "line": 43,
        "summary": (
            "`reply_pr_comments.sh` relies on callers to prefix the reply body with the "
            "`<!-- pr-review-loop-reply -->` marker so `fetch_pr_comments.sh` will drop it. "
            "If a caller ever forgets, the loop can ingest its own replies on the next fetch "
            "and repeatedly re-reply until `max_iterations`."
        ),
    }
    assert is_match(loop, bot, scorer=token_containment, threshold=CONTAINMENT_THRESHOLD) is False


def test_line_window_argument_is_honored() -> None:
    # The harness widens this to 15; a verified true pair sits at delta 13.
    summary = "git pull --ff-only relies on upstream tracking instead of explicit origin/$BRANCH"
    a = {"file": "a.sh", "line": 10, "summary": summary}
    b = {"file": "a.sh", "line": 23, "summary": summary}
    assert is_match(a, b) is False
    assert is_match(a, b, line_window=15) is True
