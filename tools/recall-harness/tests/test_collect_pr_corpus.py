"""Tests for collect_pr_corpus normalization helpers."""

import time

import pytest
from collect_pr_corpus import (  # type: ignore[import-not-found]  # noqa: E402  — sibling module made importable by conftest.py
    canonical_summary,
    finding_id,
    is_copilot_login,
    normalize_external_comment,
    parse_pr_list,
    parse_summary_bullets,
)


def test_parse_summary_bullets_anchored_bullet():
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Addressed\n"
        "- src/auth.ts:42 — missing audit log on login\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == [
        {"file": "src/auth.ts", "line": 42, "summary": "missing audit log on login"}
    ]
    assert unanchored == []


def test_parse_summary_bullets_backticked_anchor():
    """The loop emits the anchor in code ticks more often than bare. A charclass
    that excluded the backtick demoted those to unanchored, and unanchored
    findings never reach the matcher."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Addressed\n"
        "- `scripts/reply_pr_comments.sh:43` — rejects a body without the marker\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == [
        {
            "file": "scripts/reply_pr_comments.sh",
            "line": 43,
            "summary": "rejects a body without the marker",
        }
    ]
    assert unanchored == []


def test_parse_summary_bullets_backticked_anchor_with_promotion_suffix():
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Addressed\n"
        "- `src/auth.ts:42` — missing audit log — Promoted from suggestion by 2 reviewers\n"
    )
    anchored, _ = parse_summary_bullets(body)
    assert anchored == [{"file": "src/auth.ts", "line": 42, "summary": "missing audit log"}]


def test_parse_summary_bullets_colon_separator():
    """The loop separates anchor from summary with a colon as often as an em
    dash. Only the em dash anchored, so the colon form was demoted to unanchored
    and never reached the matcher."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Suggestions\n"
        "- `app/src/net/client_latency.gd:29`: UNAVAILABLE is a bare float sentinel\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == [
        {
            "file": "app/src/net/client_latency.gd",
            "line": 29,
            "summary": "UNAVAILABLE is a bare float sentinel",
        }
    ]
    assert unanchored == []


def test_parse_summary_bullets_keeps_parenthetical_in_summary():
    """A parenthetical between anchor and separator is not always a disposition
    tag: `(foreign-symlink guard)` names what the finding is about. Dropping it
    would delete the subject from the text the matcher compares."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Addressed\n"
        "- install.sh:62 (foreign-symlink guard) — the check runs after the copy\n"
        "- `src/ui/view.gd:63` (addressed): the comment was wrong\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == [
        {
            "file": "install.sh",
            "line": 62,
            "summary": "(foreign-symlink guard) the check runs after the copy",
        },
        {"file": "src/ui/view.gd", "line": 63, "summary": "(addressed) the comment was wrong"},
    ]
    assert unanchored == []


def test_parse_summary_bullets_extensionless_path_anchors_on_em_dash():
    """The colon branch needs a `.` or `/` to keep prose out, but the em dash was
    never ambiguous. Requiring it on both demoted real top-level paths that
    already anchored."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Addressed\n"
        "- `Makefile:9` — the release target skips the checksum\n"
        "- Dockerfile:4 — base image is unpinned\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == [
        {"file": "Makefile", "line": 9, "summary": "the release target skips the checksum"},
        {"file": "Dockerfile", "line": 4, "summary": "base image is unpinned"},
    ]
    assert unanchored == []


def test_parse_summary_bullets_backticked_path_may_contain_spaces():
    """The closing tick delimits the path, so whitespace inside it is not the
    end of the anchor. A code span with no `:line` before the tick is still
    prose, which is what keeps this from swallowing quoted snippets."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Suggestions\n"
        "- `docs/release notes.md:12`: the heading level skips from h2 to h4\n"
        "- `UNAVAILABLE := -1.0` is a bare float sentinel\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == [
        {
            "file": "docs/release notes.md",
            "line": 12,
            "summary": "the heading level skips from h2 to h4",
        }
    ]
    assert unanchored == [{"summary": "`UNAVAILABLE := -1.0` is a bare float sentinel"}]


def test_parse_summary_bullets_unticked_colon_anchors_on_a_slash():
    """The unticked colon form is its own branch. Everything else pinning it is a
    negative, so without this the whole branch could be deleted and stay green."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Suggestions\n"
        "- src/auth.ts:42: the audit log is written before the commit\n"
        "- tools/recall-harness/report.py:7 (nit): the docstring says buckets\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == [
        {
            "file": "src/auth.ts",
            "line": 42,
            "summary": "the audit log is written before the commit",
        },
        {
            "file": "tools/recall-harness/report.py",
            "line": 7,
            "summary": "(nit) the docstring says buckets",
        },
    ]
    assert unanchored == []


def test_parse_summary_bullets_colon_prose_stays_unanchored():
    """Admitting the colon separator must not turn `word:digits` prose into an
    anchor. An extension cannot tell a path from a host: `example.com:8080` is
    shaped exactly like a file, so an unticked anchor needs a slash."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Notes\n"
        "- 12:30: standup notes\n"
        "- localhost:8080: connection refused\n"
        "- example.com:8080: connection refused\n"
        "- v1.2.3:45: release notes\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == []
    assert unanchored == [
        {"summary": "12:30: standup notes"},
        {"summary": "localhost:8080: connection refused"},
        {"summary": "example.com:8080: connection refused"},
        {"summary": "v1.2.3:45: release notes"},
    ]


def test_parse_summary_bullets_does_not_backtrack_on_a_long_non_match():
    """Both colon patterns have had adjacent quantified classes that could
    repartition the same prefix, once around dots and once around slashes. A
    quadratic parse is seconds on a bullet this size, so pin the shape."""
    body = "<!-- pr-review-loop-summary -->\n- " + "a/" * 12000 + "\n"
    start = time.perf_counter()
    anchored, unanchored = parse_summary_bullets(body)
    # linear parses this in under a millisecond; the quadratic shape took 2.3s
    assert time.perf_counter() - start < 0.5
    assert anchored == []
    assert len(unanchored) == 1


def test_parse_summary_bullets_backticks_admit_any_path_on_a_colon():
    """Balanced backticks are the author marking an anchor, so the host/port
    ambiguity does not arise and an extensionless path is admissible."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Addressed\n"
        "- `Makefile:9`: the release target skips the checksum\n"
        "- `Dockerfile:4`: base image is unpinned\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == [
        {"file": "Makefile", "line": 9, "summary": "the release target skips the checksum"},
        {"file": "Dockerfile", "line": 4, "summary": "base image is unpinned"},
    ]
    assert unanchored == []


def test_parse_summary_bullets_backticked_path_without_line_stays_unanchored():
    """Pins that admitting the backtick widened the anchor rule and nothing else:
    no `:line`, no anchor, however the path is quoted."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Deferred\n"
        "- `templates/summary_ready.md` — no variant for a skipped CI status\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == []
    assert unanchored == [
        {"summary": "`templates/summary_ready.md` — no variant for a skipped CI status"}
    ]


def test_parse_summary_bullets_unanchored_bullet():
    body = "<!-- pr-review-loop-summary -->\n## CI\n- Sonar quality gate failed\n"
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == []
    assert unanchored == [{"summary": "Sonar quality gate failed"}]


def test_parse_summary_bullets_promotion_provenance_suffix_stripped():
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "- src/auth.ts:42 — missing audit log on login"
        " — Promoted from suggestion (agreed by 2 personas)\n"
    )
    anchored, _ = parse_summary_bullets(body)
    assert anchored[0]["summary"] == "missing audit log on login"


def test_parse_summary_bullets_no_marker_returns_empty():
    body = "Just some prose with no marker.\n- src/a.ts:1 — text\n"
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == []
    assert unanchored == []


def test_parse_summary_bullets_skips_iteration_n_template_bullets():
    """Loop's summary_ready.md template emits `- Iteration N: ...` bullets that
    describe what was fixed each iteration. These are scaffolding, not findings,
    and must not land in loop_findings_unanchored or they inflate the corpus."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Ready to merge\n\n"
        "**Reviewed across 2 iteration(s):**\n\n"
        "- Iteration 1: fixed missing audit log; added test for null path\n"
        "- Iteration 2: addressed CodeRabbit nit on error message\n\n"
        "**Deferred (out-of-scope suggestions, left as questions for the author):**\n\n"
        "- src/auth.ts:42 — consider extracting validator helper\n"
        "- Sonar quality gate flagged 0.5% extra duplicate density\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    # The anchored "Deferred" bullet still lands; the unanchored Sonar line too.
    assert anchored == [
        {"file": "src/auth.ts", "line": 42, "summary": "consider extracting validator helper"}
    ]
    # Iteration bullets are filtered out; only the Sonar bullet remains.
    assert unanchored == [{"summary": "Sonar quality gate flagged 0.5% extra duplicate density"}]


def test_normalize_external_comment_with_line():
    raw = {
        "user": {"login": "Copilot"},
        "path": "src/auth.ts",
        "line": 42,
        "body": "Consider adding an audit log here.",
        "id": 123,
        "created_at": "2026-05-10T12:00:00Z",
    }
    norm = normalize_external_comment(raw, source="copilot")
    assert norm == {
        "file": "src/auth.ts",
        "line": 42,
        "summary": "Consider adding an audit log here.",
        "source": "copilot",
        "id": 123,
        "created_at": "2026-05-10T12:00:00Z",
    }


def test_normalize_external_comment_no_line_marked_unanchored():
    raw = {
        "user": {"login": "Copilot"},
        "path": None,
        "line": None,
        "body": "Overall LGTM.",
        "id": 124,
        "created_at": "2026-05-10T12:01:00Z",
    }
    norm = normalize_external_comment(raw, source="copilot")
    assert norm["file"] is None
    assert norm["line"] is None


def test_canonical_summary_collapses_whitespace_and_strips():
    assert canonical_summary("  multi   line\n  summary  ") == "multi line summary"


def test_finding_id_is_stable_across_runs():
    f = {"file": "a.ts", "line": 10, "summary": "x", "source": "copilot"}
    assert finding_id(f) == finding_id(dict(f))


def test_finding_id_is_invariant_under_summary_whitespace():
    a = {"file": "a.ts", "line": 10, "summary": "x", "source": "copilot"}
    b = {"file": "a.ts", "line": 10, "summary": "  x  ", "source": "copilot"}
    c = {"file": "a.ts", "line": 10, "summary": "x\t\nx", "source": "copilot"}
    d = {"file": "a.ts", "line": 10, "summary": "x x", "source": "copilot"}
    assert finding_id(a) == finding_id(b)
    assert finding_id(c) == finding_id(d)


def test_finding_id_changes_with_summary_content():
    a = {"file": "a.ts", "line": 10, "summary": "x", "source": "copilot"}
    b = {"file": "a.ts", "line": 10, "summary": "y", "source": "copilot"}
    assert finding_id(a) != finding_id(b)


def test_is_copilot_login_accepts_both_forms():
    assert is_copilot_login("Copilot") is True
    assert is_copilot_login("copilot-pull-request-reviewer") is True
    assert is_copilot_login("pulsedemon") is False
    assert is_copilot_login(None) is False
    assert is_copilot_login("") is False


def test_parse_pr_list_strips_whitespace():
    assert parse_pr_list("5,9,10") == [5, 9, 10]
    assert parse_pr_list("5, 9, 10") == [5, 9, 10]
    assert parse_pr_list("  5 , 9 ,10 ") == [5, 9, 10]


def test_parse_pr_list_drops_empty_elements():
    # Trailing comma is a common typo; don't crash on it.
    assert parse_pr_list("5,9,10,") == [5, 9, 10]
    assert parse_pr_list("5,,9") == [5, 9]


def test_parse_pr_list_raises_on_non_numeric():
    with pytest.raises(ValueError):
        parse_pr_list("5, abc, 10")


def test_parse_summary_bullets_excludes_reviewer_comments_section():
    """`**Reviewer comments:**` bullets are the loop's disposition ledger — one line
    per external reviewer comment recording how the loop responded. Ingesting them as
    panel findings pairs a bot's comment with the loop's acknowledgement of that same
    comment, which is circular and inflates the match rate."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Ready to merge\n\n"
        "**Deferred (out-of-scope suggestions, left as questions for the author):**\n\n"
        "- src/auth.ts:42 — consider extracting validator helper\n\n"
        "**Reviewer comments:**\n\n"
        "- scripts/reply.sh:65 — addressed: parse failures now log a breadcrumb.\n"
        "- templates/state.schema.json:160 — deferred: needs a schema bump first.\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    assert anchored == [
        {"file": "src/auth.ts", "line": 42, "summary": "consider extracting validator helper"}
    ]
    assert unanchored == []


def test_parse_summary_bullets_inline_bold_bullet_does_not_shift_section():
    """Iteration bullets render as `- **Iteration 1** — Panel: ...`. A section-header
    match anchored on `**` must not treat a bullet body as a header, or every finding
    after one lands under the wrong section."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Ready to merge\n\n"
        "**Reviewer comments:**\n\n"
        "- **Iteration 1** — Panel: 11 reviewers, 0 blockers\n"
        "- scripts/reply.sh:65 — addressed: parse failures now log a breadcrumb.\n\n"
        "**Deferred (out-of-scope suggestions):**\n\n"
        "- src/auth.ts:42 — consider extracting validator helper\n"
    )
    anchored, unanchored = parse_summary_bullets(body)
    # The inline-bold bullet must not clear the reviewer-comments flag; if it does,
    # the `addressed:` bullet after it leaks in as a panel finding.
    assert anchored == [
        {"file": "src/auth.ts", "line": 42, "summary": "consider extracting validator helper"}
    ]
    assert unanchored == []


def test_parse_summary_bullets_keeps_deferred_wording_outside_reviewer_section():
    """Only the section decides. A Deferred finding whose text happens to start with
    "deferred"/"addressed" is a real finding and must survive."""
    body = (
        "<!-- pr-review-loop-summary -->\n"
        "## Ready to merge\n\n"
        "**Deferred (out-of-scope suggestions):**\n\n"
        "- src/tmp.ts:9 — deferred cleanup of temp dirs never runs on the error path\n"
    )
    anchored, _ = parse_summary_bullets(body)
    assert anchored == [
        {
            "file": "src/tmp.ts",
            "line": 9,
            "summary": "deferred cleanup of temp dirs never runs on the error path",
        }
    ]
