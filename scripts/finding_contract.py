#!/usr/bin/env python3
"""Shape checks for a finding persisted in `history[].findings`.

The contract itself is canonical in `templates/state.schema.json`; this module
is the runtime reading of it, shared by the scripts that re-read history[]
after the fact (`check_exit_conditions.py`, `collect_open_findings.py`,
`select_panel.py`).

The first two make decisions by *matching* persisted findings, and both are
harmed by silently dropping a malformed one: a smaller reconstructed set fires
NO_PROGRESS on a blocker set that really shrank, or hides a still-open
suggestion from the terminal summary. So anything either filter reads is
validated here, and they treat a failure as "this entry is unusable" rather
than skipping the item. `select_panel.py` runs no per-finding shape check; a
malformed history entry or promotion record makes it rerun every persona.
"""

import re

SEVERITIES = ("blocker", "suggestion", "nit")
SCOPES = ("in_scope", "out_of_scope")

# promote_findings.py annotates the summary of a finding whose evidence failed
# verification before parking it in deferred[]. The annotation is why a deferred
# record no longer compares equal to the finding it came from, so the format
# lives here rather than inline at the one site that writes it.
#
# DOTALL because the reason interpolates un-repr'd strings from LLM JSON: a
# symbol name or path with a newline in it would otherwise defeat the strip and
# the finding would render under Deferred *and* as an open suggestion.
_EVIDENCE_FAILURE_ANNOTATION = re.compile(r" \[evidence_verification_failed: .*\]$", re.DOTALL)


def annotate_evidence_failure(summary: str, reason: str) -> str:
    return f"{summary} [evidence_verification_failed: {reason}]"


def base_summary(summary: str) -> str:
    """A provenance record's summary as the finding itself wrote it."""
    return _EVIDENCE_FAILURE_ANNOTATION.sub("", summary or "")


def located_fields_ok(f: dict) -> bool:
    """Whether `file`/`line` are the types the matcher can safely compare.

    A persisted line of "88" would survive to `is_match`, which coerces with
    int(); `true` would silently become line 1, since bool is an int subclass.
    """
    if f.get("file") is not None and not isinstance(f["file"], str):
        return False
    line = f.get("line")
    return line is None or (isinstance(line, int) and not isinstance(line, bool))


def owners(f: dict) -> set[str]:
    """The personas that raised a finding.

    `source_reviewers` is the real answer and the only one a *synthesized*
    finding carries: `reviewers/output.schema.json` puts `reviewer` at the
    response level with `additionalProperties: false` on each finding, so a
    finding object never has one until something attaches it. §4c unions
    `source_reviewers` across the personas that raised the same issue, and
    `templates/state.schema.json` additionally requires a singular `reviewer` on
    each persisted finding. Hence both, in that order.

    An empty set means "owner unknown", which callers must treat as "nothing can
    speak for this finding" rather than as "nobody owns it".
    """
    sources = {r for r in f.get("source_reviewers") or [] if isinstance(r, str)}
    if sources:
        return sources
    reviewer = f.get("reviewer")
    return {reviewer} if isinstance(reviewer, str) else set()


def well_formed(f: dict, *, owner_required: bool = True) -> bool:
    """Whether a persisted finding satisfies the schema's finding contract.

    `owner_required=False` admits a finding whose owner cannot be determined.
    A caller that only *matches* findings needs the shape, not the owner, and
    rejecting the finding would drop it from the set it is reconstructing.
    """
    if not isinstance(f.get("summary"), str):
        return False
    # `reviewer` specifically, not `owners`: templates/state.schema.json requires
    # it on every persisted finding, and loosening the check here would change
    # which history entries check_exit_conditions.py trusts.
    if owner_required and not isinstance(f.get("reviewer"), str):
        return False
    if f.get("severity") not in SEVERITIES or f.get("scope") not in SCOPES:
        return False
    return located_fields_ok(f)


def well_formed_promotion(record: dict) -> bool:
    """Whether an `addressed[]`/`deferred[]` provenance record satisfies its contract."""
    if not isinstance(record.get("summary"), str):
        return False
    if not isinstance(record.get("promoted_by"), str):
        return False
    if not isinstance(record.get("source_reviewers"), list):
        return False
    return located_fields_ok(record)


def promoted_keys(entry: dict) -> set[tuple] | None:
    """return promoted finding keys, or None when provenance is unusable.

    promotions retain suggestion severity, so readers need the provenance.
    """
    keys = set()
    for record in entry.get("addressed") or []:
        if not isinstance(record, dict) or record.get("promoted_from") != "suggestion":
            continue
        if not well_formed_promotion(record):
            return None
        keys.add((record.get("file"), record.get("line"), record.get("summary")))
    return keys


def is_open_blocker(f: dict, promoted: set[tuple]) -> bool:
    """Whether a persisted finding was in its iteration's actionable blocker set.

    An out_of_scope finding never was: partition() defers it whatever its
    severity. `promoted` is the entry's `promoted_keys`.
    """
    if f.get("scope") == "out_of_scope":
        return False
    key = (f.get("file"), f.get("line"), f.get("summary"))
    return f.get("severity") == "blocker" or key in promoted
