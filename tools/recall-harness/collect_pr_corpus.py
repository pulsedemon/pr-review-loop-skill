#!/usr/bin/env python3
"""A1: Collect per-PR corpus.

For each PR in the repo (filtered by --merged-since / --pr-list; in-flight
PRs are included only when --include-open is set), fetch:
- The loop's final summary comment (identified by <!-- pr-review-loop-summary -->),
  parse its addressed/deferred/outstanding bullets into anchored {file, line, summary}
  and unanchored {summary} lists.
- All review comments, review-thread comments, and top-level reviews authored by
  any tool registered in EXTERNAL_REVIEW_TOOLS (see below). Structured-finding
  tools (currently orchestrator-review) emit one corpus entry per FINDING block
  parsed from the comment body; freeform-prose tools (currently copilot) emit
  one corpus entry per comment.
- PR's merge-commit SHA and head SHA at merge for reproducibility.

Output: tools/recall-harness/corpus/<owner>/<repo>/pr-<N>.json (one file per
PR). The owner/repo directory nesting lets the corpus hold PRs from multiple
repos without collision on PR number, and is unambiguous even when owner or
repo contain `-` (e.g. `a-b/c` vs `a/b-c`, which a flat `a-b-c-pr-N` scheme
would collide).

Normalization is deterministic: re-runs against unchanged PR state produce
byte-identical output. Comments are sorted by (file, line, created_at, id).
Summaries are whitespace-collapsed.

Recognized external review tools (currently `copilot` and `orchestrator-review`)
live in the `EXTERNAL_REVIEW_TOOLS` registry below.

Exit 0 on success, 1 on a fetch error, or 2 on a usage error. Manifest mode
prunes old records only after all fetches succeed.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from _shared import DEFAULT_CORPUS_DIR, canonical_summary

SUMMARY_MARKER = "<!-- pr-review-loop-summary -->"

# Bump on any change to normalization, marker patterns, or corpus schema.
# Readers (match_external.py, report.py) refuse corpora older than this so a
# schema mismatch fails loud instead of producing silently-wrong aggregates.
CORPUS_VERSION = 4


@dataclass(frozen=True, slots=True)
class ExternalReviewTool:
    """Identifies an external code-review tool by login plus optional body marker.

    `name` is the `source` string written to corpus entries (e.g. "copilot",
    "orchestrator-review") and used downstream by the matcher and report.
    `logins` is the set of GitHub logins the tool posts under. `body_marker`,
    if set, must appear at the start of the comment body (after leading
    whitespace). Required when a login is shared by many tools (e.g.
    `github-actions[bot]` is used by ox-security, sonarqubecloud, and in-house
    review tools, so the login alone is not a safe discriminator). Frozen
    so a module-level registry entry can't be mutated at runtime."""

    name: str
    logins: frozenset[str]
    body_marker: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ExternalReviewTool.name must be non-empty")
        if not self.logins:
            raise ValueError(f"{self.name}: logins must be non-empty")
        if self.body_marker is not None and not self.body_marker:
            raise ValueError(
                f"{self.name}: body_marker must be None or non-empty "
                "(empty string would lstrip-startswith every comment body)"
            )

    def matches(self, login: str | None, body: str | None) -> bool:
        if not login or login not in self.logins:
            return False
        if self.body_marker is None:
            return True
        if not body:
            return False
        return body.lstrip().startswith(self.body_marker)


def _validate_registry(tools: tuple[ExternalReviewTool, ...]) -> None:
    """Enforce registry-wide invariants at module load:

    1. Tool names are distinct (downstream code keys aggregates by `source`).
    2. Any login appearing in two entries has `body_marker` set on each
       (otherwise both tools claim every comment from that login, and the
       first-match-wins order silently determines the source label).
    """
    names = [t.name for t in tools]
    if len(names) != len(set(names)):
        raise RuntimeError(f"EXTERNAL_REVIEW_TOOLS has duplicate name(s): {names}")
    login_to_tools: dict[str, list[str]] = {}
    for tool in tools:
        for login in tool.logins:
            login_to_tools.setdefault(login, []).append(tool.name)
    for login, owners in login_to_tools.items():
        if len(owners) > 1:
            for tool in tools:
                if login in tool.logins and tool.body_marker is None:
                    raise RuntimeError(
                        f"login {login!r} is shared across {owners}; "
                        f"tool {tool.name!r} must set body_marker"
                    )


# see the Sources section in README.md when adding a review tool.
EXTERNAL_REVIEW_TOOLS: tuple[ExternalReviewTool, ...] = (
    ExternalReviewTool(
        name="copilot",
        logins=frozenset({"Copilot", "copilot-pull-request-reviewer"}),
    ),
    ExternalReviewTool(
        name="orchestrator-review",
        logins=frozenset({"github-actions[bot]"}),
        body_marker="<!-- ORCHESTRATOR_REVIEW |",
    ),
)

_validate_registry(EXTERNAL_REVIEW_TOOLS)

# Sources whose body emits structured FINDING blocks rather than freeform
# prose. When `identify_external_source` returns one of these and the body
# advertises FINDING blocks (matched by `_FINDING_DRIFT_PROBE`) but
# `parse_orchestrator_findings` returns no blocks, that signals upstream
# format drift and the call site raises rather than falling back to a
# whole-body unanchored finding (which would silently mask the break). The
# guard runs on all three comment-walk call sites in `collect_pr` (top-level
# issue comments, review-thread comments, top-level reviews) so a future
# change in posting venue cannot bypass it.
STRUCTURED_FINDING_SOURCES: frozenset[str] = frozenset({"orchestrator-review"})


def identify_external_source(login: str | None, body: str | None) -> ExternalReviewTool | None:
    """Return the matching registered tool, or None.

    Centralizes the recognition logic so call sites don't have to know which
    tool uses which login/marker combination. Returning the tool object (not
    just the `name` string) lets callers dispatch on the tool itself, e.g.
    `tool.name in STRUCTURED_FINDING_SOURCES`, without re-resolving."""
    for tool in EXTERNAL_REVIEW_TOOLS:
        if tool.matches(login, body):
            return tool
    return None


def corpus_filename(owner: str, repo: str, pr: int) -> str:
    """Per-PR corpus path (relative). Nests as <owner>/<repo>/pr-<N>.json so
    the corpus can hold PRs from multiple repos without collision on PR
    number. A flat `<owner>-<repo>-pr-<N>` scheme is ambiguous when owner or
    repo contain `-`, e.g. (`a-b`, `c`) and (`a`, `b-c`) would both map to
    `a-b-c-pr-<N>` and silently overwrite each other. Directory nesting on
    `/` (which neither GitHub owner nor repo names may contain) is
    unambiguous. The matched/ and unmatched/ JSONL outputs use the same
    scheme (with .jsonl extension)."""
    for part in (owner, repo):
        if (
            not isinstance(part, str)
            or not part
            or "\x00" in part
            or part in (".", "..")
            or Path(part).name != part
        ):
            raise ValueError("owner and repo must each be a single directory name")
    if type(pr) is not int or pr <= 0:
        raise ValueError("pr must be a positive integer")
    return f"{owner}/{repo}/pr-{pr}.json"


def matched_filename(owner: str, repo: str, pr: int) -> str:
    return corpus_filename(owner, repo, pr) + "l"


def parse_pr_list(raw: str) -> list[int]:
    """Parse `--pr-list` input ("5,9,10" or "5, 9, 10") into PR numbers.

    Strips whitespace and filters empty elements so a trailing comma or
    space-after-comma doesn't crash on int(). Raises ValueError (via int())
    on a genuinely non-numeric element so typos surface loudly."""
    return [int(s.strip()) for s in raw.split(",") if s.strip()]


def read_manifest(path: Path) -> list[tuple[str, str, int]]:
    """Read corpus-manifest.csv (header owner,repo,pr) into (owner, repo, pr)
    triples, in file order. csv handles quoting; pr is coerced to int so a
    non-numeric value raises loudly."""
    with path.open(newline="") as f:
        return [(r["owner"], r["repo"], int(r["pr"])) for r in csv.DictReader(f)]


def list_merged_prs(owner: str, repo: str, merged_since: str) -> list[int]:
    """PR numbers merged on or after `merged_since`, ascending.

    Shared by the collector's --merged-since mode and check_manifest_drift, so
    the drift check compares against the same population the weekly run
    collects rather than a re-derived query that could diverge from it."""
    listing_raw = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            f"{owner}/{repo}",
            "--state",
            "merged",
            "--search",
            f"merged:>={merged_since}",
            "--limit",
            "1000",
            "--json",
            "number",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(item["number"] for item in json.loads(listing_raw.stdout))


_PROMOTION_SUFFIX = r"(?:\s+\u2014\s+Promoted from suggestion.*)?$"

# optional backticks keep both summary-renderer formats anchored.
_BULLET_ANCHORED_EMDASH = re.compile(
    r"^-\s+`?(?P<file>[^\s:`]+):(?P<line>\d+)`?"
    r"(?P<note>\s*\([^)]*\))?"
    r"\s*\u2014\s+(?P<summary>.+?)" + _PROMOTION_SUFFIX,
)
# Balanced backticks are the author marking an anchor explicitly, so any path
# shape is admissible inside them: extensionless, and spaces too, since the
# closing tick delimits the path rather than the first whitespace.
_BULLET_ANCHORED_COLON_TICKED = re.compile(
    r"^-\s+`(?P<file>[^`]+):(?P<line>\d+)`"
    r"(?P<note>\s*\([^)]*\))?"
    r"\s*:\s+(?P<summary>.+?)" + _PROMOTION_SUFFIX,
)
# Unticked, nothing separates a path from prose, and an extension cannot do it:
# `example.com:8080` is shaped exactly like a file. Only a slash is decisive, so
# a bare colon anchor needs one and everything else stays prose. The leading
# segment excludes `/` so the two classes cannot repartition the same prefix
# around every slash, which backtracks quadratically on a long non-match.
_BULLET_ANCHORED_COLON_BARE = re.compile(
    r"^-\s+(?P<file>[^\s:`/]*/[^\s:`]*):(?P<line>\d+)"
    r"(?P<note>\s*\([^)]*\))?"
    r"\s*:\s+(?P<summary>.+?)" + _PROMOTION_SUFFIX,
)
_BULLET_UNANCHORED = re.compile(r"^-\s+(?P<summary>.+?)$")

# Loop summary templates (templates/summary_ready.md, summary_needs_attention.md)
# emit per-iteration scaffolding bullets like `- Iteration 1: <what was fixed>`.
# Those are not findings; capturing them inflates loop_findings_unanchored and
# wastes labeling effort. Skip any bullet whose body starts with that prefix.
_ITERATION_TEMPLATE_BULLET = re.compile(r"^Iteration\s+\d+:")

# The summary templates emit a `**Reviewer comments:**` section holding one bullet per
# external reviewer comment, recording how the loop responded (`addressed:` / `deferred:`).
# Those are dispositions, not panel findings: ingesting them pairs a bot's comment with the
# loop's acknowledgement of that same comment. Matched on non-bullet lines only, because
# bullet bodies can contain inline bold without introducing a new section.
_SECTION_HEADER = re.compile(r"^\*\*(?P<title>.+?):?\*\*")
_REVIEWER_COMMENTS_SECTION = "reviewer comments"


def parse_summary_bullets(body: str) -> tuple[list[dict], list[dict]]:
    """Parse the loop's summary comment body into anchored and unanchored bullets.

    Anchored bullets follow `- file:line \u2014 summary [\u2014 Promoted from ...]`. The
    promotion suffix is stripped from the summary used for matching.
    Unanchored bullets are any other `- ...` line, except the loop's own
    `- Iteration N: ...` template scaffolding which is dropped. Bullets under a
    `**Reviewer comments:**` header are dropped too; see _SECTION_HEADER. Bullets
    only counted when the SUMMARY_MARKER is present in body."""
    if SUMMARY_MARKER not in body:
        return [], []
    anchored: list[dict] = []
    unanchored: list[dict] = []
    in_reviewer_comments = False
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line.startswith("- "):
            header = _SECTION_HEADER.match(line)
            if header:
                in_reviewer_comments = (
                    header.group("title").strip().lower() == _REVIEWER_COMMENTS_SECTION
                )
            continue
        if in_reviewer_comments:
            continue
        m = (
            _BULLET_ANCHORED_EMDASH.match(line)
            or _BULLET_ANCHORED_COLON_TICKED.match(line)
            or _BULLET_ANCHORED_COLON_BARE.match(line)
        )
        if m:
            # The parenthetical is not always a disposition tag to discard:
            # `(foreign-symlink guard)` is the finding's subject. Keep it in the
            # summary so matching sees the same words a reader does.
            note = (m.group("note") or "").strip()
            summary = f"{note} {m.group('summary')}" if note else m.group("summary")
            anchored.append(
                {
                    "file": m.group("file"),
                    "line": int(m.group("line")),
                    "summary": canonical_summary(summary),
                }
            )
            continue
        m2 = _BULLET_UNANCHORED.match(line)
        if m2:
            summary = canonical_summary(m2.group("summary"))
            if _ITERATION_TEMPLATE_BULLET.match(summary):
                continue
            unanchored.append({"summary": summary})
    return anchored, unanchored


def normalize_external_comment(raw: dict, source: str) -> dict:
    """Normalize an external review-thread comment to corpus shape.

    `source` is the registered tool name (see EXTERNAL_REVIEW_TOOLS).
    """
    return {
        "file": raw.get("path"),
        "line": raw.get("line"),
        "summary": canonical_summary(raw.get("body", "")),
        "source": source,
        "id": raw.get("id"),
        "created_at": raw.get("created_at"),
    }


# ORCHESTRATOR_REVIEW bodies emit one FINDING block per finding:
#
#   <!-- FINDING: <SEVERITY> | <file> | <agent> | L<startLine> | L<endLine> -->
#   <!-- TITLE: <title> -->
#   <prose>
#
# We anchor on the start line and use TITLE as the summary. Severity is parsed
# but not stored, the labeler's job to decide miss vs noise vs out_of_scope.
_FINDING_BLOCK = re.compile(
    r"<!--\s*FINDING:\s*(?P<severity>[A-Z]+)\s*\|\s*(?P<file>[^|]+?)\s*\|\s*"
    r"(?P<agent>[^|]+?)\s*\|\s*L(?P<start>\d+)\s*\|\s*L(?P<end>\d+)\s*-->\s*"
    r"<!--\s*TITLE:\s*(?P<title>.+?)\s*-->",
    re.DOTALL,
)

# Drift probe used to decide between "format drift" and "clean LGTM" when a
# structured-finding tool's comment has no parsed FINDING blocks. Deliberately
# laxer than _FINDING_BLOCK (case-insensitive) so a casing change upstream
# surfaces as a loud raise instead of a silent skip.
_FINDING_DRIFT_PROBE = re.compile(r"<!--\s*FINDING:", re.IGNORECASE)


def parse_orchestrator_findings(body: str) -> list[dict]:
    """Extract per-finding entries from an ORCHESTRATOR_REVIEW comment body.

    Returns a list of partial-shape dicts ({file, line, summary}) one per
    FINDING block; caller fills in source/id/created_at from the parent comment.
    Bodies without any FINDING blocks return []; safe to call on any comment.

    Reject blank paths because they identify no file."""
    if not body:
        return []
    out: list[dict] = []
    for m in _FINDING_BLOCK.finditer(body):
        file_part = m.group("file").strip()
        if not file_part:
            raise RuntimeError(
                "parse_orchestrator_findings: FINDING block has empty file "
                f"segment (line={m.group('start')}, title={m.group('title')!r}). "
                "Upstream is emitting whitespace-only file slots."
            )
        out.append(
            {
                "file": file_part,
                "line": int(m.group("start")),
                "summary": canonical_summary(m.group("title")),
            }
        )
    return out


def _gh_api(path: str) -> list:
    """Call `gh api <path> --paginate` and return a flat list of JSON objects.

    `gh api --paginate` concatenates pages as a stream of JSON arrays; we decode
    each and flatten."""
    result = subprocess.run(
        ["gh", "api", path, "--paginate"],
        check=True,
        capture_output=True,
        text=True,
    )
    decoder = json.JSONDecoder()
    out: list = []
    s = result.stdout.strip()
    if not s:
        raise json.JSONDecodeError(f"empty gh response for {path}", s, 0)
    i = 0
    while i < len(s):
        obj, end = decoder.raw_decode(s, i)
        if isinstance(obj, list):
            out.extend(obj)
        else:
            out.append(obj)
        i = end
        while i < len(s) and s[i].isspace():
            i += 1
    return out


def collect_pr(owner: str, repo: str, pr_number: int, include_open: bool = False) -> dict:
    """Build the corpus dict for a single PR.

    Collects: the loop's summary comment (anchored + unanchored bullets), any
    review-thread or top-level reviews from registered external review tools,
    and any structured FINDING blocks from top-level issue comments matching
    a registered tool's marker. Sources recognized are listed in
    EXTERNAL_REVIEW_TOOLS.

    Open PRs are skipped by default so the corpus reflects frozen post-merge
    state (re-running the harness later produces the same record). Pass
    `include_open=True` to label in-flight PRs; the record's `merged_at` and
    `merge_commit_sha` will be null and `head_sha_at_merge` carries the head
    sha at corpus time, which can drift as the PR is updated."""
    pr_meta_raw = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--repo",
            f"{owner}/{repo}",
            "--json",
            "title,mergedAt,mergeCommit,headRefOid,baseRefName,headRefName",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    pr_meta = json.loads(pr_meta_raw.stdout)
    merged_at = pr_meta.get("mergedAt")
    if not merged_at and not include_open:
        return {"corpus_version": CORPUS_VERSION, "pr": pr_number, "skipped": "not merged"}
    is_open = merged_at is None

    # 1. Top-level issue comments. The loop's summary lives here; so do
    #    structured external reviews like ORCHESTRATOR_REVIEW that emit
    #    multiple FINDING blocks in a single comment body.
    issue_comments = _gh_api(f"repos/{owner}/{repo}/issues/{pr_number}/comments")
    loop_anchored: list[dict] = []
    loop_unanchored: list[dict] = []
    loop_summary_created_at: str | None = None
    loop_summary_edited_at: str | None = None
    external: list[dict] = []
    for c in issue_comments:
        body = c.get("body") or ""
        if SUMMARY_MARKER in body:
            loop_anchored, loop_unanchored = parse_summary_bullets(body)
            # A1 sees only the current body. A summary edited after an external
            # reviewer commented can carry bullets paraphrasing that comment, which
            # would otherwise score as recall the panel never earned. Equal
            # timestamps mean GitHub recorded no edit.
            loop_summary_created_at = c.get("created_at")
            updated_at = c.get("updated_at")
            loop_summary_edited_at = updated_at if updated_at != loop_summary_created_at else None
            continue
        login = (c.get("user") or {}).get("login")
        tool = identify_external_source(login, body)
        if tool is None:
            continue
        findings = parse_orchestrator_findings(body)
        if findings:
            for f in findings:
                external.append(
                    {
                        **f,
                        "source": tool.name,
                        "id": c.get("id"),
                        "created_at": c.get("created_at"),
                    }
                )
        elif tool.name in STRUCTURED_FINDING_SOURCES:
            # Marker matched, no FINDING blocks parsed. Two cases:
            # (a) The body advertises FINDING blocks (looks like "<!-- FINDING:"
            #     anywhere, case-insensitive) but the parser missed all of them.
            #     Upstream format has drifted (FINDING renamed, L<n> anchor
            #     dropped, severity lowercased, etc.), refuse to silently fall
            #     back to a whole-body unanchored finding because that would
            #     mask the break. Case-insensitive on purpose: a casing change
            #     upstream is itself a drift we want to surface, not skip.
            # (b) The body has no findings (e.g. "No issues found.
            #     LGTM!"). Record nothing, there's nothing to label.
            if _FINDING_DRIFT_PROBE.search(body):
                raise RuntimeError(
                    f"{owner}/{repo} PR #{pr_number} comment id={c.get('id')}: "
                    f"source={tool.name!r} body advertises FINDING blocks but "
                    "zero parsed. Upstream format may have changed and "
                    "_FINDING_BLOCK needs updating."
                )
            # else: clean approval comment, skip silently.
        else:
            external.append(
                {
                    "file": None,
                    "line": None,
                    "summary": canonical_summary(body),
                    "source": tool.name,
                    "id": c.get("id"),
                    "created_at": c.get("created_at"),
                }
            )

    # 2. Review-thread comments (line-anchored).
    review_comments = _gh_api(f"repos/{owner}/{repo}/pulls/{pr_number}/comments")
    for raw in review_comments:
        login = (raw.get("user") or {}).get("login")
        body = raw.get("body") or ""
        tool = identify_external_source(login, body)
        if tool is None:
            continue
        if tool.name in STRUCTURED_FINDING_SOURCES and _FINDING_DRIFT_PROBE.search(body):
            raise RuntimeError(
                f"{owner}/{repo} PR #{pr_number} review comment id={raw.get('id')}: "
                f"source={tool.name!r} body advertises FINDING blocks but the "
                "review-thread call site does not parse them. Either upstream "
                "started posting structured findings on a new venue or "
                "_FINDING_BLOCK needs updating; refuse to silently drop."
            )
        external.append(normalize_external_comment(raw, source=tool.name))

    # 3. Top-level reviews (typically summary-only, no file/line).
    reviews = _gh_api(f"repos/{owner}/{repo}/pulls/{pr_number}/reviews")
    for raw in reviews:
        login = (raw.get("user") or {}).get("login")
        body = raw.get("body") or ""
        tool = identify_external_source(login, body)
        if tool is not None and body.strip():
            if tool.name in STRUCTURED_FINDING_SOURCES and _FINDING_DRIFT_PROBE.search(body):
                raise RuntimeError(
                    f"{owner}/{repo} PR #{pr_number} review id={raw.get('id')}: "
                    f"source={tool.name!r} body advertises FINDING blocks but the "
                    "top-level-review call site does not parse them. Either "
                    "upstream started posting structured findings on a new venue "
                    "or _FINDING_BLOCK needs updating; refuse to silently drop."
                )
            external.append(
                {
                    "file": None,
                    "line": None,
                    "summary": canonical_summary(body),
                    "source": tool.name,
                    "id": raw.get("id"),
                    "created_at": raw.get("submitted_at"),
                }
            )

    # Deterministic sort: (file or "", line or 0, created_at or "", id or 0).
    external.sort(
        key=lambda f: (
            f.get("file") or "",
            f.get("line") or 0,
            f.get("created_at") or "",
            f.get("id") or 0,
        )
    )

    return {
        "corpus_version": CORPUS_VERSION,
        "pr": pr_number,
        "owner": owner,
        "repo": repo,
        "title": pr_meta.get("title"),
        "merged_at": merged_at,
        "merge_commit_sha": (pr_meta.get("mergeCommit") or {}).get("oid"),
        "head_sha_at_merge": pr_meta.get("headRefOid"),
        "base_ref": pr_meta.get("baseRefName"),
        "head_ref": pr_meta.get("headRefName"),
        "is_open": is_open,
        "loop_findings": loop_anchored,
        "loop_findings_unanchored": loop_unanchored,
        "loop_summary_created_at": loop_summary_created_at,
        "loop_summary_edited_at": loop_summary_edited_at,
        "external_findings": external,
    }


_FETCH_ERRORS = (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError)


def _fetch_error_detail(error: Exception) -> str:
    detail = f"{type(error).__name__}: {error}"
    if isinstance(error, subprocess.CalledProcessError) and error.stderr:
        detail += f"\nstderr: {error.stderr}"
    return detail


def _collect_and_write(
    owner: str, repo: str, pr_numbers: list[int], out_dir: Path, include_open: bool
) -> bool:
    out_dir.mkdir(parents=True, exist_ok=True)
    for pr in pr_numbers:
        try:
            record = collect_pr(owner, repo, pr, include_open=include_open)
        except _FETCH_ERRORS as error:
            print(
                f"collect_pr_corpus: cannot collect {owner}/{repo} PR #{pr}\n"
                f"{_fetch_error_detail(error)}",
                file=sys.stderr,
            )
            return False
        out_path = out_dir / corpus_filename(owner, repo, pr)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(f"wrote {out_path}", file=sys.stderr)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="A1: collect per-PR corpus")
    parser.add_argument("--owner")
    parser.add_argument("--repo")
    parser.add_argument(
        "--pr-list",
        type=parse_pr_list,
        help="Comma-separated PR numbers. Mutually exclusive with --merged-since.",
    )
    parser.add_argument(
        "--merged-since",
        help="ISO date (YYYY-MM-DD). Collect all merged PRs on or after this date.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_CORPUS_DIR,
    )
    parser.add_argument(
        "--include-open",
        action="store_true",
        help=(
            "Include open (not-yet-merged) PRs. Off by default so the corpus "
            "reflects frozen post-merge state. Use for in-flight diagnosis; "
            "merged_at/merge_commit_sha will be null in the resulting record."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help=(
            "Path to corpus-manifest.csv. Collects exactly the listed PRs "
            "(reproducibility mode). Mutually exclusive with "
            "--owner/--repo/--pr-list/--merged-since."
        ),
    )
    args = parser.parse_args()

    single_repo_mode = any(
        value is not None for value in (args.owner, args.repo, args.pr_list, args.merged_since)
    )
    if args.manifest and single_repo_mode:
        parser.error(
            "--manifest is mutually exclusive with --owner/--repo/--pr-list/--merged-since"
        )
    if not args.manifest and not single_repo_mode:
        parser.error("provide --manifest, or --owner/--repo with --pr-list/--merged-since")

    if args.manifest:
        if args.include_open:
            parser.error(
                "--include-open is not valid with --manifest (the manifest lists merged PRs)"
            )
        # Reproducibility mode: collect exactly the manifest's PRs, grouped by
        # repo. A repo the current token cannot reach is a hard error (not a
        # silent skip), a partial corpus would defeat the point. Use the
        # single-repo flags to collect a subset on purpose.
        grouped: dict[tuple[str, str], list[int]] = {}
        expected_paths = set()
        for owner, repo, pr in read_manifest(args.manifest):
            grouped.setdefault((owner, repo), []).append(pr)
            expected_paths.add(args.out_dir / corpus_filename(owner, repo, pr))
        for (owner, repo), prs in grouped.items():
            if not _collect_and_write(owner, repo, prs, args.out_dir, include_open=False):
                print(
                    "Manifest collection needs access to every listed repository. "
                    "Stopped before pruning. "
                    "Use --owner/--repo/--pr-list to collect a subset.",
                    file=sys.stderr,
                )
                return 1
        args.out_dir.mkdir(parents=True, exist_ok=True)
        # prune only after every requested record was collected successfully.
        for path in args.out_dir.glob("*/*/pr-*.json"):
            if path not in expected_paths:
                path.unlink()
        return 0

    # Single-repo mode (discovery / ad-hoc).
    if not args.owner or not args.repo:
        parser.error("--owner and --repo are required without --manifest")

    if not args.pr_list and not args.merged_since:
        # Without either, the merged-listing branch below would build the
        # malformed search "merged:>=None"; require one explicitly.
        parser.error("provide --pr-list or --merged-since in single-repo mode")

    if args.pr_list is not None and args.merged_since is not None:
        parser.error("--pr-list and --merged-since are mutually exclusive")

    if args.include_open and not args.pr_list:
        parser.error(
            "--include-open requires --pr-list; --merged-since lists only merged PRs "
            "(gh pr list is invoked with --state merged)"
        )

    if args.pr_list:
        pr_numbers = args.pr_list
    else:
        try:
            pr_numbers = list_merged_prs(args.owner, args.repo, args.merged_since)
        except _FETCH_ERRORS as error:
            print(
                f"collect_pr_corpus: cannot collect {args.owner}/{args.repo}: "
                f"listing merged PRs since {args.merged_since}\n{_fetch_error_detail(error)}",
                file=sys.stderr,
            )
            return 1
    if not _collect_and_write(
        args.owner, args.repo, pr_numbers, args.out_dir, include_open=args.include_open
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
