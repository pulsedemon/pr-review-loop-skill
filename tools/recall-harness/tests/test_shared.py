"""Tests for the shared helpers module."""

from _shared import (  # type: ignore[import-not-found]  # noqa: E402  — sibling module made importable by conftest.py
    canonical_summary,
    finding_id,
)


def test_canonical_summary_collapses_whitespace():
    assert canonical_summary("  multi   line\n  summary  ") == "multi line summary"


def test_canonical_summary_preserves_case():
    assert canonical_summary("HELLO World") == "HELLO World"


def test_finding_id_is_stable():
    f = {"file": "a.ts", "line": 10, "summary": "x", "source": "copilot"}
    assert finding_id(f) == finding_id(dict(f))


def test_finding_id_invariant_to_whitespace_in_summary():
    a = {"file": "a.ts", "line": 10, "summary": "x y", "source": "copilot"}
    b = {"file": "a.ts", "line": 10, "summary": "x   y", "source": "copilot"}
    assert finding_id(a) == finding_id(b)


def test_finding_id_changes_with_meaning_change():
    a = {"file": "a.ts", "line": 10, "summary": "x", "source": "copilot"}
    b = {"file": "a.ts", "line": 10, "summary": "y", "source": "copilot"}
    assert finding_id(a) != finding_id(b)


def test_finding_id_a1_and_a2_byte_equal_after_extraction():
    """A1 and A2 must import from _shared so their hashes can't drift."""
    from collect_pr_corpus import finding_id as a1_finding_id  # type: ignore[import-not-found]
    from match_external import finding_id_for as a2_finding_id  # type: ignore[import-not-found]

    f = {"file": "src/a.ts", "line": 42, "summary": "missing audit log", "source": "copilot"}
    assert a1_finding_id(f) == finding_id(f)
    assert a2_finding_id(f) == finding_id(f)
