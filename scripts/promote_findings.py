#!/usr/bin/env python3
"""Partition deduped reviewer findings into the synthesis action plan.

Owns all three promotion paths the skill uses:

  - multi_source                   (existing rule, moved out of the §4c synthesis prompt)
  - adversary_endorsed             (adversary co-signs a panel suggestion; SKILL.md §4d.0.5)
  - evidence_gated_solo_adversary  (solo adversary finding with verified evidence; §4d.0.5)

Reads one JSON object on stdin. The findings input has two mutually exclusive shapes:

  findings:           list of deduped findings (single-list mode), OR
  panel_findings:     list of panel findings    (split mode; merged with the next field
  adversary_findings: list of adversary findings via _merge_adversary before partitioning;
  an in-scope adversary blocker retains its diagnostic payload when matched to a suggestion or nit)

Other required top-level fields (both modes):

  suggestion_promotion_threshold: int (>=0); 0 disables multi_source promotion
  adversary_promotion:            bool; false disables suggestion endorsement promotion
  adversary_solo_promotion:       bool; false disables the solo-adversary path
  demoted:                        list of this iteration's demoted entries

Emits a single JSON object on stdout with:

  blockers, suggestions, nits, addressed, deferred

Exit codes:
  0 - success
  2 - schema / usage error (stderr describes)
"""

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from finding_contract import annotate_evidence_failure  # noqa: E402
from finding_matcher import LINE_WINDOW  # noqa: E402
from finding_matcher import is_match as _is_match  # noqa: E402

# Cap on file size for _verify_evidence reads. finding_evidence.file is sourced
# from LLM-produced JSON; without a cap, a multi-GB lockfile or generated asset
# would read into memory before the line/symbol/snippet checks.
_MAX_EVIDENCE_FILE_BYTES = 5 * 1024 * 1024


def _merge_adversary(panel: list, adversary: list) -> list:
    """keep scope disagreements separate and retain an explicit blocker's diagnostics."""
    merged = [dict(p, source_reviewers=list(p.get("source_reviewers", []))) for p in panel]
    for adv in adversary:
        matched = False
        for index, p in enumerate(merged):
            if p.get("scope") != adv.get("scope") or not _is_match(p, adv):
                continue
            if (
                p.get("severity") in ("suggestion", "nit")
                and adv.get("severity") == "blocker"
                and adv.get("scope") == "in_scope"
            ):
                sources = p["source_reviewers"]
                if p.get("reviewer") and p["reviewer"] not in sources:
                    sources.append(p["reviewer"])
                merged[index] = dict(adv, source_reviewers=sources)
            if "adversary" not in merged[index]["source_reviewers"]:
                merged[index]["source_reviewers"].append("adversary")
            matched = True
        if not matched:
            merged.append(
                dict(adv, source_reviewers=list(adv.get("source_reviewers", ["adversary"])))
            )
    return merged


def _die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _require(obj: dict, key: str, expected_type) -> None:
    if key not in obj:
        _die(f"missing required field '{key}'")
    if expected_type is int:
        if isinstance(obj[key], bool) or not isinstance(obj[key], int):
            _die(f"'{key}' must be int")
        return
    if not isinstance(obj[key], expected_type):
        _die(f"'{key}' must be {expected_type.__name__}")


def _plain_deferred(f: dict) -> str:
    file_ = f.get("file", "?")
    line = f.get("line", "?")
    summary = f.get("summary", "")
    return f"`{file_}:{line}`: {summary}"


def _provenance(f: dict, promoted_by: str, reason: str) -> dict:
    return {
        "file": f["file"],
        "line": f["line"],
        "summary": f["summary"],
        "promoted_from": "suggestion",
        "promoted_by": promoted_by,
        "promotion_reason": reason,
        "source_reviewers": list(f.get("source_reviewers", [])),
    }


def _coerce_line(value):
    # bool is a subclass of int; reject it to match the existing `_require(..., int)`
    # convention. demoted[] and finding_evidence come from LLM JSON, so anything
    # else (str, None, float) yields None and the caller handles it.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _objected(finding_evidence: dict, demoted: list) -> bool:
    """True iff `demoted[]` contains an entry within ±5 lines on the same file."""
    target_file = finding_evidence["file"]
    target_line = _coerce_line(finding_evidence.get("line"))
    if target_line is None:
        return False
    for d in demoted:
        if d.get("file") != target_file:
            continue
        d_line = _coerce_line(d.get("line"))
        if d_line is None:
            continue
        if abs(d_line - target_line) <= LINE_WINDOW:
            return True
    return False


def _adversary_endorsed_eligible(f: dict, endorsement_promotion: bool) -> bool:
    """endorsement promotion is independent of the multi-source threshold."""
    if not endorsement_promotion:
        return False
    if f.get("severity") != "suggestion":
        return False
    if f.get("scope") != "in_scope":
        return False
    sources = set(f.get("source_reviewers") or [])
    return "adversary" in sources and len(sources) >= 2


def _verify_evidence(ev: dict) -> tuple:
    """bound untrusted evidence reads to repository files; return validity and a failure reason."""
    raw = ev["file"]
    if not isinstance(raw, str) or not raw:
        return False, f"file must be non-empty string (got {raw!r})"
    if os.path.isabs(raw):
        return False, f"path outside repo: {raw}"
    cwd = Path.cwd().resolve()
    try:
        resolved = (cwd / raw).resolve()
        resolved.relative_to(cwd)
    except (ValueError, OSError):
        return False, f"path outside repo: {raw}"
    path = resolved
    if not path.is_file():
        return False, f"file not found: {raw}"
    try:
        size = path.stat().st_size
    except OSError as e:
        return False, f"cannot stat {raw}: {e}"
    if size > _MAX_EVIDENCE_FILE_BYTES:
        return (
            False,
            f"file too large to verify: {raw} ({size} bytes > {_MAX_EVIDENCE_FILE_BYTES} cap)",
        )
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return False, f"cannot read {raw}: {e}"
    if text == "":
        line_count = 0
    else:
        line_count = text.count("\n") + (0 if text.endswith("\n") else 1)
    ev_line = _coerce_line(ev.get("line"))
    if ev_line is None:
        return False, f"line must be integer (got {ev.get('line')!r})"
    if line_count == 0 or not (1 <= ev_line <= line_count):
        return False, f"line {ev_line} out of bounds (file has {line_count} lines)"
    if "symbol" in ev:
        sym = ev["symbol"]
        if not isinstance(sym, str):
            return False, f"symbol must be string (got {sym!r})"
        if sym not in text:
            return False, f"symbol '{sym}' not present in {raw}"
    if "snippet" in ev:
        snip = ev["snippet"]
        if not isinstance(snip, str):
            return False, f"snippet must be string (got {snip!r})"
        if snip not in text:
            return False, f"snippet not present in {raw}"
    return True, ""


def _solo_adversary_eligible(f: dict, solo_promotion: bool, demoted: list) -> bool:
    """All four gate conditions from spec §2."""
    if not solo_promotion:
        return False
    if f.get("severity") != "suggestion":
        return False
    if f.get("scope") != "in_scope":
        return False
    sources = f.get("source_reviewers") or []
    if list(sources) != ["adversary"]:
        return False
    ev = f.get("finding_evidence")
    if not isinstance(ev, dict):
        return False
    if "file" not in ev or "line" not in ev:
        return False
    if "symbol" not in ev and "snippet" not in ev:
        return False
    if _objected(ev, demoted):
        return False
    return True


def partition(findings, threshold, endorsement_promotion, solo_promotion, demoted):
    out = {
        "blockers": [],
        "suggestions": [],
        "nits": [],
        "addressed": [],
        "deferred": [],
    }

    for f in findings:
        scope = f.get("scope")
        severity = f.get("severity")

        if scope == "out_of_scope":
            out["deferred"].append(_plain_deferred(f))
            continue

        if severity == "blocker":
            out["blockers"].append(f)
            continue

        if severity == "nit":
            out["nits"].append(f)
            continue

        # path order matters: endorsement runs first so it wins over multi-source
        # and preserves promoted_by="adversary" attribution.
        if _adversary_endorsed_eligible(f, endorsement_promotion):
            out["blockers"].append(f)
            out["addressed"].append(_provenance(f, "adversary", "adversary_endorsed"))
            continue

        sources = f.get("source_reviewers", [])
        distinct_sources = set(sources)
        distinct_count = len(distinct_sources)

        # solo-adversary findings must route through the evidence-gated path
        # (which verifies finding_evidence and respects the demoted[] objection
        # check). without this guard, threshold=1 would let any solo-adversary
        # suggestion satisfy `distinct_count >= threshold` and promote via the
        # multi-source path, bypassing evidence verification entirely.
        if threshold > 0 and distinct_count >= threshold and distinct_sources != {"adversary"}:
            out["blockers"].append(f)
            out["addressed"].append(_provenance(f, "multi-persona", "multi_source"))
            continue

        if _solo_adversary_eligible(f, solo_promotion, demoted):
            ok, reason = _verify_evidence(f["finding_evidence"])
            if ok:
                out["blockers"].append(f)
                out["addressed"].append(
                    _provenance(f, "adversary", "evidence_gated_solo_adversary")
                )
            else:
                deferred_obj = _provenance(f, "adversary", "evidence_verification_failed")
                deferred_obj["summary"] = annotate_evidence_failure(f["summary"], reason)
                out["deferred"].append(deferred_obj)
            continue

        out["suggestions"].append(f)

    return out


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(f"invalid JSON on stdin: {e}")

    if not isinstance(data, dict):
        _die("stdin must be a JSON object")

    has_findings = "findings" in data
    has_split = "panel_findings" in data or "adversary_findings" in data
    if has_findings and has_split:
        _die("provide either 'findings' or 'panel_findings'+'adversary_findings', not both")

    _require(data, "suggestion_promotion_threshold", int)
    _require(data, "adversary_promotion", bool)
    _require(data, "adversary_solo_promotion", bool)
    _require(data, "demoted", list)

    if has_split:
        _require(data, "panel_findings", list)
        _require(data, "adversary_findings", list)
        findings = _merge_adversary(data["panel_findings"], data["adversary_findings"])
    else:
        _require(data, "findings", list)
        findings = data["findings"]

    plan = partition(
        findings,
        data["suggestion_promotion_threshold"],
        data["adversary_promotion"],
        data["adversary_solo_promotion"],
        data["demoted"],
    )
    json.dump(plan, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
