"""Tests for the fail-loud schema guards added alongside the CORPUS_VERSION
bump: CORPUS_VERSION reader-guard in match_external + report, _load_labels
column validation in report, and the orchestrator-no-FINDING fail-loud in
collect_pr."""

import csv
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import collect_pr_corpus  # type: ignore[import-not-found]  # noqa: E402
import pytest
from collect_pr_corpus import (  # type: ignore[import-not-found]  # noqa: E402
    CORPUS_VERSION,
    collect_pr,
    corpus_filename,
)
from report import _load_labels  # type: ignore[import-not-found]  # noqa: E402

HARNESS = Path(__file__).resolve().parents[1]
MATCH_SCRIPT_PATH = HARNESS / "match_external.py"
REPORT_SCRIPT_PATH = HARNESS / "report.py"
REPO_MATCH_FINDINGS = HARNESS.parent.parent / "scripts" / "match_findings.py"


def test_load_labels_raises_on_legacy_5_column_csv(tmp_path):
    """missing repository columns would join labels to the wrong finding population."""
    path = tmp_path / "labels.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pr", "bucket", "finding_id", "label", "notes"])
        w.writerow(["1", "unmatched", "abc", "real_miss", ""])
    with pytest.raises(RuntimeError, match="missing required column 'owner'"):
        _load_labels(path)


def test_load_labels_raises_on_csv_missing_repo_column(tmp_path):
    path = tmp_path / "labels.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["owner", "pr", "bucket", "finding_id", "label", "notes"])
        w.writerow(["o", "1", "unmatched", "abc", "real_miss", ""])
    with pytest.raises(RuntimeError, match="missing required column 'repo'"):
        _load_labels(path)


def test_load_labels_returns_empty_when_file_absent(tmp_path):
    # Backward-compat: an absent labels.csv is not an error (first-run case).
    assert _load_labels(tmp_path / "labels.csv") == {}


def _write_corpus(corpus_dir: Path, owner: str, repo: str, pr: int, record: dict) -> Path:
    """Write a corpus record at the canonical nested path; create parents."""
    out_path = corpus_dir / corpus_filename(owner, repo, pr)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record))
    return out_path


def _legacy_v1_corpus(pr: int = 1) -> dict:
    # Pre-PR-30 shape (no owner/repo, corpus_version=1).
    return {
        "corpus_version": 1,
        "pr": pr,
        "loop_findings": [],
        "loop_findings_unanchored": [],
        "external_findings": [],
    }


def test_match_external_rejects_legacy_corpus_version(tmp_path):
    # Legacy corpus needs owner/repo in the filename for match_external to
    # find it; we supply them in the filename but not the body. The
    # version guard fires before the missing-key lookup.
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write_corpus(corpus_dir, "o", "r", 1, _legacy_v1_corpus(1))
    result = subprocess.run(
        [
            sys.executable,
            str(MATCH_SCRIPT_PATH),
            "--corpus-dir",
            str(corpus_dir),
            "--unmatched-dir",
            str(tmp_path / "unmatched"),
            "--matched-dir",
            str(tmp_path / "matched"),
            "--loop-unmatched-dir",
            str(tmp_path / "loop_unmatched"),
            "--match-script",
            str(REPO_MATCH_FINDINGS),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "corpus_version=1" in result.stderr
    assert "Re-run collect_pr_corpus.py" in result.stderr


def test_match_external_rejects_legacy_flat_layout(tmp_path):
    """A corpus_dir containing the pre-PR-30 flat layout (`pr-<N>.json`
    at top level) with no nested files makes `glob('*/*/pr-*.json')`
    yield nothing, so the per-file CORPUS_VERSION guard never fires.
    Without the nested-layout guard, A2 would exit 0 with no work —
    swallowing the same schema-mismatch signal the version bump
    exists to surface."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "pr-1.json").write_text(json.dumps(_legacy_v1_corpus(1)))
    result = subprocess.run(
        [
            sys.executable,
            str(MATCH_SCRIPT_PATH),
            "--corpus-dir",
            str(corpus_dir),
            "--unmatched-dir",
            str(tmp_path / "unmatched"),
            "--matched-dir",
            str(tmp_path / "matched"),
            "--loop-unmatched-dir",
            str(tmp_path / "loop_unmatched"),
            "--match-script",
            str(REPO_MATCH_FINDINGS),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "legacy flat corpus layout detected" in result.stderr
    assert "Re-run collect_pr_corpus.py" in result.stderr


def test_report_rejects_legacy_corpus_version(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write_corpus(corpus_dir, "o", "r", 1, _legacy_v1_corpus(1))
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
    assert "corpus_version=1" in result.stderr
    assert "Re-run collect_pr_corpus.py" in result.stderr


def test_report_rejects_legacy_flat_layout(tmp_path):
    """Same as the match_external case: when the nested glob yields
    nothing but the corpus_dir holds the legacy flat layout, report.py
    must surface the schema mismatch instead of writing an empty
    `PRs analyzed: 0` report with exit 0."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "pr-1.json").write_text(json.dumps(_legacy_v1_corpus(1)))
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
    assert "legacy flat corpus layout detected" in result.stderr
    assert "Re-run collect_pr_corpus.py" in result.stderr


def test_report_accepts_current_corpus_version(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    record = {
        "corpus_version": CORPUS_VERSION,
        "pr": 1,
        "owner": "o",
        "repo": "r",
        "loop_findings": [],
        "loop_findings_unanchored": [],
        "external_findings": [],
    }
    _write_corpus(corpus_dir, "o", "r", 1, record)
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
            "--loop-unmatched-dir",
            str(tmp_path / "loop_unmatched"),
            "--labels",
            str(tmp_path / "labels.csv"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "PRs analyzed: 1" in result.stdout


def test_report_surfaces_in_flight_prs_separately(tmp_path):
    """Records collected with --include-open carry is_open=True and must be
    excluded from totals/per-repo aggregates but surfaced in a dedicated
    section so the operator knows they exist."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    open_record = {
        "corpus_version": CORPUS_VERSION,
        "pr": 99,
        "owner": "o",
        "repo": "r",
        "merged_at": None,
        "is_open": True,
        "loop_findings": [],
        "loop_findings_unanchored": [],
        "external_findings": [{"file": "a.ts", "line": 1, "summary": "x", "source": "copilot"}],
    }
    merged_record = {
        "corpus_version": CORPUS_VERSION,
        "pr": 1,
        "owner": "o",
        "repo": "r",
        "merged_at": "2026-05-01T00:00:00Z",
        "is_open": False,
        "loop_findings": [],
        "loop_findings_unanchored": [],
        "external_findings": [{"file": "a.ts", "line": 1, "summary": "y", "source": "copilot"}],
    }
    _write_corpus(corpus_dir, "o", "r", 99, open_record)
    _write_corpus(corpus_dir, "o", "r", 1, merged_record)
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
            "--loop-unmatched-dir",
            str(tmp_path / "loop_unmatched"),
            "--labels",
            str(tmp_path / "labels.csv"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "In-flight PRs (excluded from totals)" in result.stdout
    assert "o/r PR #99" in result.stdout
    # The merged record's anchored external must appear in totals; the open
    # one must NOT. Total external is 1, not 2.
    assert "External findings: 1" in result.stdout


class _StubGhPrView:
    """Stand-in for subprocess.run when called for `gh pr view ...`. Returns a
    fake PR metadata blob with mergedAt set so collect_pr proceeds past the
    skip-not-merged short-circuit."""

    def __init__(self, merged: bool = True):
        self.merged = merged

    def __call__(self, *args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if "view" not in cmd:
            raise AssertionError(f"unexpected subprocess.run call: {cmd}")

        class Result:
            stdout = json.dumps(
                {
                    "number": 99,
                    "title": "t",
                    "author": {"login": "x"},
                    "mergedAt": "2026-05-01T00:00:00Z" if self.merged else None,
                    "mergeCommit": {"oid": "abc"} if self.merged else None,
                    "headRefOid": "def",
                    "baseRefName": "main",
                    "headRefName": "feat",
                    "body": "",
                }
            )

        return Result()


def _fake_gh_api(issue_comments=None, review_comments=None, reviews=None):
    """Return a _gh_api replacement that routes by URL path suffix."""
    issue_comments = issue_comments or []
    review_comments = review_comments or []
    reviews = reviews or []

    def _api(path: str) -> list:
        if path.endswith("/comments") and "/issues/" in path:
            return issue_comments
        if path.endswith("/comments") and "/pulls/" in path:
            return review_comments
        if path.endswith("/reviews"):
            return reviews
        raise AssertionError(f"unexpected _gh_api call: {path}")

    return _api


def test_collect_pr_raises_on_orchestrator_body_advertising_findings_with_zero_parsed():
    """If the body contains `<!-- FINDING:` substrings but the parser extracts
    zero blocks, the upstream format has drifted. collect_pr raises rather
    than silently dropping data."""
    issue_comments = [
        {
            "id": 555,
            "created_at": "2026-05-02T00:00:00Z",
            "user": {"login": "github-actions[bot]"},
            "body": (
                "<!-- ORCHESTRATOR_REVIEW | COMMIT: abc -->\n"
                # malformed FINDING block (missing TITLE line) — parser yields 0
                "<!-- FINDING: IMPORTANT | src/a.ts | x | L1 | L2 -->\n"
                "no TITLE line follows\n"
            ),
        }
    ]
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api(issue_comments)),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=True)
        with pytest.raises(RuntimeError, match="advertises FINDING blocks but zero parsed"):
            collect_pr("o", "r", 99)


@pytest.mark.parametrize(
    "drift_marker",
    [
        "<!-- finding:",  # casing drift (all lowercase)
        "<!-- Finding:",  # casing drift (titlecase)
    ],
)
def test_collect_pr_raises_on_orchestrator_drift_in_marker_casing(drift_marker):
    """The drift guard must catch realistic upstream format changes — not just
    a malformed-but-uppercase FINDING block. A casing change to the FINDING
    marker itself is the most likely drift mode (someone normalizes the
    orchestrator's HTML-comment generator) and the silent-skip behavior the
    case-sensitive substring check previously had would have masked it.
    The drift probe is case-insensitive so the strict _FINDING_BLOCK still
    fails to parse the lowercase form (correct), but the probe still fires
    (correct) → RuntimeError raised."""
    issue_comments = [
        {
            "id": 555,
            "created_at": "2026-05-02T00:00:00Z",
            "user": {"login": "github-actions[bot]"},
            "body": (
                "<!-- ORCHESTRATOR_REVIEW | COMMIT: abc -->\n"
                f"{drift_marker} IMPORTANT | src/a.ts | x | L1 | L2 -->\n"
                "<!-- TITLE: example -->\n"
            ),
        }
    ]
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api(issue_comments)),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=True)
        with pytest.raises(RuntimeError, match="advertises FINDING blocks but zero parsed"):
            collect_pr("o", "r", 99)


def test_collect_pr_skips_orchestrator_no_issues_lgtm_comment():
    """A clean approval comment ('No issues found. LGTM!') has the
    ORCHESTRATOR_REVIEW marker but no FINDING blocks. There's nothing to
    record; the harness must not raise."""
    issue_comments = [
        {
            "id": 666,
            "created_at": "2026-05-02T00:00:00Z",
            "user": {"login": "github-actions[bot]"},
            "body": (
                "<!-- ORCHESTRATOR_REVIEW | COMMIT: abc -->\n\n"
                "Automated PR Review: No issues found. LGTM!\n"
            ),
        }
    ]
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api(issue_comments)),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=True)
        record = collect_pr("o", "r", 99)
    # Comment is recognized but contributes no external findings.
    assert record["external_findings"] == []


def test_collect_pr_raises_on_orchestrator_finding_marker_in_review_thread_comment():
    """The drift guard owns all three comment-walk call sites. If a future
    orchestrator-review version posts a FINDING-marker body via a review-thread
    comment (which today goes through normalize_external_comment without
    FINDING parsing), the guard must fire — never silently drop the structured
    body."""
    review_comments = [
        {
            "id": 777,
            "user": {"login": "github-actions[bot]"},
            "path": "src/a.ts",
            "line": 1,
            "body": (
                "<!-- ORCHESTRATOR_REVIEW | COMMIT: abc -->\n"
                "<!-- FINDING: IMPORTANT | src/a.ts | x | L1 | L2 -->\n"
                "<!-- TITLE: drift on review-thread -->\n"
            ),
        }
    ]
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api(review_comments=review_comments)),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=True)
        with pytest.raises(
            RuntimeError,
            match="review-thread call site does not parse them",
        ):
            collect_pr("o", "r", 99)


def test_collect_pr_raises_on_orchestrator_finding_marker_in_top_level_review():
    """Same guard, third call site: a top-level review whose body advertises
    FINDING blocks must raise rather than be recorded as an unanchored
    summary that silently drops the structured content."""
    reviews = [
        {
            "id": 888,
            "submitted_at": "2026-05-02T00:00:00Z",
            "user": {"login": "github-actions[bot]"},
            "body": (
                "<!-- ORCHESTRATOR_REVIEW | COMMIT: abc -->\n"
                "<!-- FINDING: IMPORTANT | src/a.ts | x | L1 | L2 -->\n"
                "<!-- TITLE: drift on top-level review -->\n"
            ),
        }
    ]
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api(reviews=reviews)),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=True)
        with pytest.raises(
            RuntimeError,
            match="top-level-review call site does not parse them",
        ):
            collect_pr("o", "r", 99)


@pytest.mark.parametrize(
    "drift_marker",
    [
        "<!-- finding:",  # casing drift (all lowercase)
        "<!-- Finding:",  # casing drift (titlecase)
    ],
)
def test_collect_pr_raises_on_orchestrator_drift_in_marker_casing_review_thread(drift_marker):
    """Casing-drift sibling of the issue-comments parametric test, for the
    review-thread call site. A future revert from regex to a literal-substring
    check at this venue must fail tests, not pass silently."""
    review_comments = [
        {
            "id": 778,
            "user": {"login": "github-actions[bot]"},
            "path": "src/a.ts",
            "line": 1,
            "body": (
                "<!-- ORCHESTRATOR_REVIEW | COMMIT: abc -->\n"
                f"{drift_marker} IMPORTANT | src/a.ts | x | L1 | L2 -->\n"
                "<!-- TITLE: drift on review-thread -->\n"
            ),
        }
    ]
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api(review_comments=review_comments)),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=True)
        with pytest.raises(
            RuntimeError,
            match="review-thread call site does not parse them",
        ):
            collect_pr("o", "r", 99)


@pytest.mark.parametrize(
    "drift_marker",
    [
        "<!-- finding:",  # casing drift (all lowercase)
        "<!-- Finding:",  # casing drift (titlecase)
    ],
)
def test_collect_pr_raises_on_orchestrator_drift_in_marker_casing_top_level_review(drift_marker):
    """Casing-drift sibling for the top-level-review call site."""
    reviews = [
        {
            "id": 889,
            "submitted_at": "2026-05-02T00:00:00Z",
            "user": {"login": "github-actions[bot]"},
            "body": (
                "<!-- ORCHESTRATOR_REVIEW | COMMIT: abc -->\n"
                f"{drift_marker} IMPORTANT | src/a.ts | x | L1 | L2 -->\n"
                "<!-- TITLE: drift on top-level review -->\n"
            ),
        }
    ]
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api(reviews=reviews)),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=True)
        with pytest.raises(
            RuntimeError,
            match="top-level-review call site does not parse them",
        ):
            collect_pr("o", "r", 99)


def test_collect_pr_records_orchestrator_review_thread_comment_without_finding_marker():
    """Negative companion: a recognized orchestrator-review comment posted via
    review-thread that does NOT carry a FINDING marker stays on the freeform
    normalize_external_comment path — the guard must not over-fire."""
    review_comments = [
        {
            "id": 779,
            "user": {"login": "github-actions[bot]"},
            "path": "src/a.ts",
            "line": 5,
            "body": ("<!-- ORCHESTRATOR_REVIEW | COMMIT: abc -->\nLooks fine to me.\n"),
        }
    ]
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api(review_comments=review_comments)),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=True)
        record = collect_pr("o", "r", 99)
    sources = {f["source"] for f in record["external_findings"]}
    assert sources == {"orchestrator-review"}


def test_collect_pr_stamps_is_open_true_for_unmerged_pr_with_include_open():
    """--include-open lets the harness label in-flight PRs. The record must
    carry is_open=True so report.py can exclude it from totals."""
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api()),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=False)
        record = collect_pr("o", "r", 99, include_open=True)
    assert record["is_open"] is True
    assert record["merged_at"] is None


def test_collect_pr_stamps_is_open_false_for_merged_pr():
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api()),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=True)
        record = collect_pr("o", "r", 99)
    assert record["is_open"] is False
    assert record["merged_at"] == "2026-05-01T00:00:00Z"


def test_collect_pr_mixed_source_deterministic_sort():
    """A PR with both Copilot review-thread comments AND an orchestrator-review
    issue comment must produce a stable cross-source sort. The sort key is
    (file or '', line or 0, created_at or '', id or 0)."""
    issue_comments = [
        {
            "id": 100,
            "created_at": "2026-05-02T12:00:00Z",
            "user": {"login": "github-actions[bot]"},
            "body": (
                "<!-- ORCHESTRATOR_REVIEW | COMMIT: abc -->\n"
                "<!-- FINDING: IMPORTANT | src/b.ts | x | L10 | L12 -->\n"
                "<!-- TITLE: title B -->\nprose\n"
            ),
        }
    ]
    review_comments = [
        {
            "id": 200,
            "created_at": "2026-05-02T11:00:00Z",
            "user": {"login": "Copilot"},
            "path": "src/a.ts",
            "line": 5,
            "body": "issue here",
        },
        {
            "id": 201,
            "created_at": "2026-05-02T11:30:00Z",
            "user": {"login": "Copilot"},
            "path": "src/b.ts",
            "line": 10,
            "body": "different issue",
        },
    ]
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api(issue_comments, review_comments)),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=True)
        record = collect_pr("o", "r", 99)
    files_lines = [(f["file"], f["line"], f["source"]) for f in record["external_findings"]]
    # Sorted by (file, line, created_at, id). src/a.ts:5 < src/b.ts:10 (two
    # entries at b.ts:10: copilot at 11:30 sorts before orchestrator at 12:00).
    assert files_lines == [
        ("src/a.ts", 5, "copilot"),
        ("src/b.ts", 10, "copilot"),
        ("src/b.ts", 10, "orchestrator-review"),
    ]


def test_validate_registry_rejects_duplicate_names():
    """The _validate_registry hook prevents two entries claiming the same
    source name (downstream code keys aggregates by source)."""
    from collect_pr_corpus import (  # type: ignore[import-not-found]
        ExternalReviewTool,
        _validate_registry,
    )

    with pytest.raises(RuntimeError, match="duplicate name"):
        _validate_registry(
            (
                ExternalReviewTool(name="copilot", logins=frozenset({"a"})),
                ExternalReviewTool(name="copilot", logins=frozenset({"b"})),
            )
        )


def test_validate_registry_rejects_shared_login_without_marker():
    """If two entries share a login, both must set body_marker — otherwise
    first-match-wins silently claims every comment from that login."""
    from collect_pr_corpus import (  # type: ignore[import-not-found]
        ExternalReviewTool,
        _validate_registry,
    )

    with pytest.raises(RuntimeError, match="shared"):
        _validate_registry(
            (
                ExternalReviewTool(
                    name="a",
                    logins=frozenset({"shared-bot"}),
                    body_marker="<!-- A",
                ),
                # Same login, no marker — silent claim of every shared-bot comment.
                ExternalReviewTool(name="b", logins=frozenset({"shared-bot"})),
            )
        )


def test_main_rejects_include_open_with_merged_since(tmp_path):
    """`gh pr list --state merged` is hardcoded on the --merged-since path, so
    combining --include-open with --merged-since silently never returned open
    PRs. main() now hard-errors out to surface the limitation."""
    collect_script = HARNESS / "collect_pr_corpus.py"
    result = subprocess.run(
        [
            sys.executable,
            str(collect_script),
            "--owner",
            "o",
            "--repo",
            "r",
            "--merged-since",
            "2026-01-01",
            "--include-open",
            "--out-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--include-open requires --pr-list" in result.stderr


def test_corpus_filename_disambiguates_when_owner_or_repo_contain_dash():
    """A flat `<owner>-<repo>-pr-<N>` scheme is ambiguous when owner or repo
    contain `-`: (`a-b`, `c`) and (`a`, `b-c`) both reduce to
    `a-b-c-pr-<N>`. The current scheme nests on `/`, which neither GitHub
    owner nor repo names may contain, so the two paths must differ."""
    a = corpus_filename("a-b", "c", 1)
    b = corpus_filename("a", "b-c", 1)
    assert a != b
    # Nested layout is what makes the disambiguation possible.
    assert a == "a-b/c/pr-1.json"
    assert b == "a/b-c/pr-1.json"


def test_load_labels_raises_on_empty_csv_with_bad_header(tmp_path):
    """Header validation must run against reader.fieldnames before the row
    loop. Otherwise a malformed-header + zero-row CSV silently returns `{}`
    and the fail-loud schema guard never fires."""
    path = tmp_path / "labels.csv"
    # Bad header (missing owner/repo), zero data rows.
    path.write_text("pr,bucket,finding_id,label,notes\n")
    with pytest.raises(RuntimeError, match="missing required column 'owner'"):
        _load_labels(path)


def test_load_labels_raises_on_csv_missing_label_column(tmp_path):
    """The required-column set must include `label` — otherwise a CSV
    missing that column gets past the header check and crashes with a
    KeyError deep inside the row loop instead of the documented
    RuntimeError schema-mismatch message."""
    path = tmp_path / "labels.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["owner", "repo", "pr", "bucket", "finding_id", "notes"])
        w.writerow(["o", "r", "1", "unmatched", "abc", ""])
    with pytest.raises(RuntimeError, match="missing required column 'label'"):
        _load_labels(path)


def test_collect_pr_records_summary_edit_provenance():
    """A1 collects the CURRENT summary body, so a summary edited after an external
    reviewer commented may contain bullets paraphrasing that comment. Without the
    timestamps nothing downstream can tell a panel finding from an echo, and the
    pair would be scored as recall the panel never earned."""
    issue_comments = [
        {
            "id": 1,
            "created_at": "2026-05-19T22:19:49Z",
            "updated_at": "2026-05-19T22:52:38Z",
            "user": {"login": "someone"},
            "body": (
                "<!-- pr-review-loop-summary -->\n"
                "**Deferred (out-of-scope suggestions):**\n\n"
                "- scripts/sync_skill.sh:48 — git pull relies on upstream tracking\n"
            ),
        }
    ]
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api(issue_comments)),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=True)
        record = collect_pr("o", "r", 99)

    assert record["loop_summary_created_at"] == "2026-05-19T22:19:49Z"
    assert record["loop_summary_edited_at"] == "2026-05-19T22:52:38Z"


def test_collect_pr_summary_edited_at_is_none_when_never_edited():
    """created_at == updated_at means GitHub never recorded an edit; storing None
    keeps "unedited" distinguishable from "edited at the moment of creation"."""
    issue_comments = [
        {
            "id": 1,
            "created_at": "2026-06-05T20:34:18Z",
            "updated_at": "2026-06-05T20:34:18Z",
            "user": {"login": "someone"},
            "body": ("<!-- pr-review-loop-summary -->\n- src/a.ts:1 — a finding\n"),
        }
    ]
    with (
        patch.object(collect_pr_corpus, "subprocess") as mock_sub,
        patch.object(collect_pr_corpus, "_gh_api", _fake_gh_api(issue_comments)),
    ):
        mock_sub.run.side_effect = _StubGhPrView(merged=True)
        record = collect_pr("o", "r", 99)

    assert record["loop_summary_created_at"] == "2026-06-05T20:34:18Z"
    assert record["loop_summary_edited_at"] is None


def test_load_labels_raises_on_unknown_bucket(tmp_path):
    """Buckets are join keys read at three hard-coded call sites. A typo'd bucket
    is silently dropped, so the row looks labeled while contributing nothing."""
    path = tmp_path / "labels.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["owner", "repo", "pr", "bucket", "finding_id", "label", "notes"])
        w.writerow(["o", "r", "1", "unmatchd", "abc", "real_miss", ""])
    with pytest.raises(RuntimeError, match="unknown bucket 'unmatchd'"):
        _load_labels(path)


def test_load_labels_raises_on_label_from_another_bucket(tmp_path):
    """Labels are bucket-scoped. `real_miss` in loop_unmatched would land in the
    precision denominator's `unlabeled` bin while reading as a real judgment."""
    path = tmp_path / "labels.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["owner", "repo", "pr", "bucket", "finding_id", "label", "notes"])
        w.writerow(["o", "r", "1", "loop_unmatched", "abc", "real_miss", ""])
    with pytest.raises(RuntimeError, match="label 'real_miss' is not valid for bucket"):
        _load_labels(path)


def test_load_labels_accepts_the_committed_labels_file():
    """The real artifact must satisfy the validator it just gained."""
    _load_labels(Path(__file__).resolve().parents[1] / "labels.csv")


def test_committed_labels_rows_have_no_overflow_field():
    """an extra CSV field escapes named-column validation and breaks a DictWriter round trip."""
    with (Path(__file__).resolve().parents[1] / "labels.csv").open(newline="") as f:
        overflow = [i for i, row in enumerate(csv.DictReader(f), start=2) if None in row]
    assert overflow == [], f"labels.csv rows with an unquoted comma in notes (lines): {overflow}"
