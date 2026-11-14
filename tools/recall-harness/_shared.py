"""Shared helpers for the recall harness.

Single source of truth for `canonical_summary()` and `finding_id()` so the
hash A1 emits and the hash A2 reads stay byte-identical. Labels in
labels.csv key on `finding_id`; if A1 and A2 ever disagreed on the hash,
every label would silently fail to join.
"""

from __future__ import annotations

import hashlib
import json


def canonical_summary(s: str) -> str:
    """Collapse whitespace, strip. Case preserved for readable labels.csv
    output; the matcher lowercases internally."""
    return " ".join(s.split())


def finding_id(finding: dict) -> str:
    """Stable hash over (file, line, source, canonical_summary)."""
    payload = json.dumps(
        {
            "file": finding.get("file"),
            "line": finding.get("line"),
            "source": finding.get("source"),
            "summary": canonical_summary(finding.get("summary", "")),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
