"""Tests for the external-review-tool registry and orchestrator-review parser.

The registry (`EXTERNAL_REVIEW_TOOLS` in collect_pr_corpus.py) is the single
source of truth for which logins + body markers count as an external review.
These tests pin the recognized sources, the dispatch logic in
`identify_external_source`, and the structured-finding parser used for tools
whose body emits multiple FINDING blocks per comment.

A synthetic real-shape fixture (orchestrator-review-sample.md) anchors the
orchestrator-review parser tests so regressions in marker matching or block
extraction surface immediately."""

from pathlib import Path

from collect_pr_corpus import (  # type: ignore[import-not-found]  # noqa: E402  — sibling module made importable by conftest.py
    EXTERNAL_REVIEW_TOOLS,
    ExternalReviewTool,
    identify_external_source,
    parse_orchestrator_findings,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_registry_includes_copilot_and_orchestrator_review():
    names = {t.name for t in EXTERNAL_REVIEW_TOOLS}
    assert "copilot" in names
    assert "orchestrator-review" in names


def test_registry_marker_only_required_for_shared_logins():
    """Tools sharing a login with many other actions (github-actions[bot])
    must set body_marker; tools with a dedicated login may omit it. This pins
    the discriminator strategy so a future entry can't quietly add a shared
    login without a marker (which would misclassify unrelated comments)."""
    shared_logins = {"github-actions[bot]"}
    for tool in EXTERNAL_REVIEW_TOOLS:
        if tool.logins & shared_logins:
            assert tool.body_marker is not None, (
                f"tool {tool.name!r} uses shared login {tool.logins} "
                "and must set body_marker for safe discrimination"
            )


def test_external_review_tool_matches_login_only():
    tool = ExternalReviewTool(name="x", logins=frozenset({"alice"}))
    assert tool.matches("alice", "anything") is True
    assert tool.matches("alice", None) is True
    assert tool.matches("bob", "anything") is False


def test_external_review_tool_matches_login_and_marker():
    tool = ExternalReviewTool(name="x", logins=frozenset({"alice"}), body_marker="<!-- MARKER")
    assert tool.matches("alice", "<!-- MARKER --> body") is True
    assert tool.matches("alice", "  <!-- MARKER --> body") is True  # tolerates leading ws
    assert tool.matches("alice", "not the marker") is False
    assert tool.matches("alice", None) is False
    assert tool.matches("bob", "<!-- MARKER --> body") is False


def test_identify_external_source_returns_copilot_for_copilot_logins():
    tool = identify_external_source("Copilot", None)
    assert tool is not None and tool.name == "copilot"
    tool = identify_external_source("copilot-pull-request-reviewer", None)
    assert tool is not None and tool.name == "copilot"
    tool = identify_external_source("copilot-pull-request-reviewer", "any body")
    assert tool is not None and tool.name == "copilot"


def test_identify_external_source_returns_orchestrator_review_for_marker_match():
    body = "<!-- ORCHESTRATOR_REVIEW | COMMIT: abc -->\nsome text"
    tool = identify_external_source("github-actions[bot]", body)
    assert tool is not None and tool.name == "orchestrator-review"


def test_identify_external_source_skips_actions_bot_without_marker():
    """ox-security, sonarqubecloud, and many other tools also post as
    github-actions[bot]. Without the ORCHESTRATOR_REVIEW marker they must not
    be misclassified as external reviews — that would corrupt the candidate-
    miss bucket with unrelated bot chatter."""
    ox_body = (
        '<img src="https://www.ox.security/wp-content/uploads/2022/06/logo.svg" '
        'alt="OX Security Logo" width="250">\n\n'
        "OX Security reviewed this pull request — **nothing to fix.**\n"
    )
    assert identify_external_source("github-actions[bot]", ox_body) is None


def test_identify_external_source_returns_none_for_unknown_logins():
    assert identify_external_source("pulsedemon", "some body") is None
    assert identify_external_source(None, "some body") is None
    assert identify_external_source("", "") is None


def test_parse_orchestrator_findings_extracts_all_blocks_from_sample():
    """The synthetic fixture has 5 FINDING blocks across 4 distinct
    (file, line) keys, with one file (widget.ts) carrying two findings at the
    same line. Re-record the fixture if upstream changes the block format;
    this test pins the parser to that exact shape."""
    body = (FIXTURES / "orchestrator-review-sample.md").read_text()
    findings = parse_orchestrator_findings(body)
    assert len(findings) == 5

    summaries_by_file = {(f["file"], f["line"]): f["summary"] for f in findings}
    assert ("src/types/widget.ts", 35) in summaries_by_file
    assert ("src/types/item.ts", 42) in summaries_by_file
    assert ("src/components/DetailHero.tsx", 87) in summaries_by_file
    assert ("src/components/__tests__/ItemCard.test.tsx", 74) in summaries_by_file

    # Same file appears twice (two distinct findings on widget.ts:35) —
    # parser must surface both.
    widget_findings = [f for f in findings if f["file"].endswith("widget.ts")]
    assert len(widget_findings) == 2


def test_parse_orchestrator_findings_returns_empty_for_unrelated_body():
    assert parse_orchestrator_findings("") == []
    assert parse_orchestrator_findings("just prose, no markers") == []
    # A marker without any FINDING blocks still returns [] (the wrapper alone
    # carries no findings).
    assert parse_orchestrator_findings("<!-- ORCHESTRATOR_REVIEW | foo -->\n") == []


def test_parse_orchestrator_findings_raises_on_empty_file_segment():
    """a whitespace-only file field identifies no file."""
    import pytest

    body = (
        "<!-- ORCHESTRATOR_REVIEW | COMMIT: abc -->\n"
        # whitespace-only file segment between the pipes
        "<!-- FINDING: IMPORTANT |   | comment-analyzer | L10 | L12 -->\n"
        "<!-- TITLE: example -->\n"
    )
    with pytest.raises(RuntimeError, match="empty file segment"):
        parse_orchestrator_findings(body)


def test_external_review_tool_rejects_empty_name():
    import pytest

    with pytest.raises(ValueError, match="name must be non-empty"):
        ExternalReviewTool(name="", logins=frozenset({"x"}))


def test_external_review_tool_rejects_empty_logins():
    import pytest

    with pytest.raises(ValueError, match="logins must be non-empty"):
        ExternalReviewTool(name="x", logins=frozenset())


def test_external_review_tool_rejects_empty_body_marker():
    """Empty-string body_marker would lstrip-startswith every comment body,
    collapsing the discriminator. Must be None or non-empty."""
    import pytest

    with pytest.raises(ValueError, match="body_marker must be None or non-empty"):
        ExternalReviewTool(name="x", logins=frozenset({"y"}), body_marker="")


def test_external_review_tool_rejects_marker_not_at_lstrip_start():
    """The marker check uses body.lstrip().startswith(marker). A marker
    appearing mid-body (e.g. inside a code block or quoted text) must not
    cause a false-positive match."""
    tool = ExternalReviewTool(name="x", logins=frozenset({"a"}), body_marker="<!-- MARK")
    assert tool.matches("a", "prefix <!-- MARK --> body") is False
    assert tool.matches("a", "\nprefix\n<!-- MARK --> body") is False


def test_external_review_tool_is_frozen():
    """Module-level registry entries can't be mutated at runtime, which would
    otherwise let a caller silently break the registry's discriminator."""
    from dataclasses import FrozenInstanceError

    import pytest

    tool = ExternalReviewTool(name="x", logins=frozenset({"a"}))
    with pytest.raises(FrozenInstanceError):
        tool.name = "y"  # type: ignore[misc]


def test_parse_orchestrator_findings_summary_is_title_not_severity():
    """The summary used for matching is the TITLE text, not severity or agent
    name. This pins the contract because the matcher's containment scoring depends
    on the title vocabulary, not the structural metadata."""
    body = (
        "<!-- ORCHESTRATOR_REVIEW | COMMIT: deadbeef -->\n"
        "<!-- FINDING: IMPORTANT | src/x.ts | comment-analyzer | L10 | L12 -->\n"
        "<!-- TITLE: precise summary text -->\n"
        "prose\n"
    )
    findings = parse_orchestrator_findings(body)
    assert findings == [{"file": "src/x.ts", "line": 10, "summary": "precise summary text"}]
