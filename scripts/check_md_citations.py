#!/usr/bin/env python3
"""Check that markdown path citations resolve.

Two rules over every tracked .md file (fixture and frozen trees excluded):

  1. A backticked span that looks like a repo file path must name a git-tracked
     file when resolved from the repo root. File-relative citations are rejected
     on purpose: prose gets quoted and paraphrased across files, and a path that
     only resolves from one directory misleads everywhere else — a single line
     mixing a root-relative `docs/...` citation with a directory-local
     `tests/...` citation reads correctly under no convention at all.
  2. A markdown link target must resolve file-relatively (GitHub link
     semantics) to a tracked file or directory.

Generated-by-design artifacts that prose legitimately cites are allowlisted.

Exit codes: 0 clean, 1 violations (one per line on stdout), 2 setup error.
"""

import os
import re
import subprocess
import sys

# Content-specific excludes, deliberately local (same convention as the
# dev-tree consumers): scenario fixtures describe fictional PRs whose paths
# are part of the fiction, and docs/superpowers holds frozen historical
# specs excluded from every drift guard.
EXCLUDE_PREFIXES = ("tests/scenarios/", "docs/superpowers/")

# Gitignored artifacts the docs cite as generated-by-design.
ALLOWED_GENERATED = {"tools/recall-harness/REPORT.md"}

# A span is only treated as a path citation when it ends in one of these.
EXTS = (".md", ".py", ".sh", ".yaml", ".yml", ".json", ".bats", ".csv", ".jsonl")

# Placeholder or glob characters mean the span is a template, not a citation.
PLACEHOLDER_CHARS = set("<>{}*$ ")

SPAN_RE = re.compile(r"`([^`\n]+)`")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s[^)]*)?\)")


def tracked_files() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout
    return {p for p in out.split("\0") if p}


def span_path(span: str) -> str | None:
    """The repo path a backticked span cites, or None if it is not a citation."""
    if PLACEHOLDER_CHARS & set(span):
        return None
    if span.startswith(("http://", "https://", "mailto:", "~", ".git/")):
        return None
    path = span.split("#")[0].split("::")[0]
    path = path.removeprefix("./")
    if "/" not in path or not path.endswith(EXTS):
        return None
    return path


def link_target(target: str, from_dir: str) -> str | None:
    """The repo path a markdown link points at, or None if it is external."""
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return None
    if PLACEHOLDER_CHARS & set(target):
        return None
    path = target.split("#")[0]
    if not path:
        return None
    return os.path.normpath(os.path.join(from_dir, path))


def is_tracked_dir(path: str, tracked: set[str]) -> bool:
    prefix = path.rstrip("/") + "/"
    return any(p.startswith(prefix) for p in tracked)


def main() -> int:
    try:
        tracked = tracked_files()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"check_md_citations: cannot list tracked files: {exc}", file=sys.stderr)
        return 2

    violations = []
    md_files = [
        f for f in sorted(tracked) if f.endswith(".md") and not f.startswith(EXCLUDE_PREFIXES)
    ]
    for md in md_files:
        text = open(md, encoding="utf-8").read()
        from_dir = os.path.dirname(md)
        for m in SPAN_RE.finditer(text):
            path = span_path(m.group(1))
            if path is None or path in tracked or path in ALLOWED_GENERATED:
                continue
            line = text.count("\n", 0, m.start()) + 1
            violations.append(
                f"{md}:{line}: `{m.group(1)}` does not name a tracked file from the repo root"
            )
        for m in LINK_RE.finditer(text):
            path = link_target(m.group(1), from_dir)
            if path is None or path in tracked or path in ALLOWED_GENERATED:
                continue
            if is_tracked_dir(path, tracked):
                continue
            line = text.count("\n", 0, m.start()) + 1
            violations.append(
                f"{md}:{line}: link target ({m.group(1)}) resolves to untracked {path}"
            )

    for v in violations:
        print(v)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
