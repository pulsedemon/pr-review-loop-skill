#!/usr/bin/env python3
# collect_open_findings.py: the still-open suggestion and nit sets for Step 5.
#
# Step 5 renders its suggestion and nit bullets from one iteration's
# synthesized partitions. On a delta-gated run the persona that raised an
# earlier one may not have run again, so that finding sits in
# history[].findings, counted in n_suggestions / n_nits, and is never shown.
# This script walks history[] plus the current iteration and returns the ones
# still open. See docs/step5-summary.md#carrying-open-suggestions-and-nits.
#
# stdin: {
#   iteration: int,                the iteration Step 5 is exiting from:
#                                  `state.iteration + 1` on every exit before
#                                  §4i appended it, `state.iteration` on the
#                                  §4d.1 SUCCESS path which appended an entry
#                                  (carrying `findings: []` in older state),
#                                  and `0` before any iteration ran. The number is what tells the
#                                  first two apart; see _rounds.
#   suggestions: [finding],        this iteration's synthesized partitions,
#   nits: [finding],               passed through from promote_findings.py.
#                                  An owner is read from `source_reviewers`
#                                  (or `reviewer`, on a persisted finding);
#                                  without one the item is never settled by
#                                  the owner test.
#   blockers: [finding]|null,      supersession only, never rendered from
#                                  here. A suggestion promoted to blocker is
#                                  listed under Outstanding blockers and must
#                                  not also render as an open suggestion.
#   findings: [finding]|null,     raw current findings, including out_of_scope
#   deferred: [str|record]|null,  this iteration's deferrals; records settle
#                                  failed-evidence suggestions by their source key
#   panel_ran: [str]|null,         personas §4a.1 selected this iteration
#   reviewer_errors: [obj]|null,   of those, the ones whose output failed
#   shallow_review: [str]|null,    validation or came back shallow: selected,
#                                  but no verdict to speak with
#   adversary: obj|null,           §4d.0's record for this iteration, shaped
#   adversary_shallow_giveup: bool like history[]'s. The adversary is not a
#                                  panel persona, so panel_ran cannot say it
#                                  reviewed, and its two shallow states mean it
#                                  did not (docs/adversary.md).
#   forced_full_sweep: bool|null   true when the pre-approval sweep ran the
#                                  full panel (docs/delta-gate.md)
# }
# argv: --state <path to <git-dir>/pr-loop/state.json>
#
# stdout: {
#   suggestions: [item],
#   nits: [item],
#   carried: int                   items first raised before `iteration`
# }
# item = {file?, line?, summary, first_seen_iteration}.
#
# `reviewer` is deliberately dropped from every item: the posted comment must
# not claim attribution (docs/step5-summary.md), and a field that never
# reaches the renderer cannot leak into it.
#
# exit codes:
#   0: emitted the open sets
#   2: usage / malformed input
#
# Matching rule: docs/synthesis.md.

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from finding_contract import (  # noqa: E402
    base_summary,
    owners,
    well_formed,
    well_formed_promotion,
)
from finding_matcher import is_match_or_summary, token_overlap  # noqa: E402
from pr_loop_state import StateValidationError, load_state  # noqa: E402

OPEN_SEVERITIES = ("suggestion", "nit")
ADVERSARY = "adversary"


def _key(record: dict) -> tuple:
    return (record.get("file"), record.get("line"), record.get("summary"))


def _settled(entry: dict) -> set[tuple]:
    """Provenance records for findings this entry promoted or deferred.

    promote_findings.py appends a promoted suggestion to blockers[] without
    rewriting `severity`, and routes a failed evidence check to deferred[] the
    same way, so severity alone cannot tell an open suggestion from one that
    already has a home elsewhere in the summary. addressed[]/deferred[] carry
    the provenance record for exactly those.

    Keys, not the matcher: `_provenance` copies `file`/`line`/`summary` off the
    finding verbatim, so exact equality is exhaustive here, and the §4c window
    is not an equivalence relation, so a fuzzy check would let one promotion
    retire a *different* finding within five lines of it, which would then
    render in no section at all.

    The deferred record's summary is annotated with the verification failure
    before it is parked, so the key is built from the summary the finding itself
    wrote (`base_summary`); comparing the annotated text would never fire and
    that finding would render under Deferred *and* as an open suggestion.

    A malformed provenance record is skipped rather than fatal: the cost is one
    finding rendered in two sections, against losing every carried finding on
    the entry. That is the opposite tradeoff from check_exit_conditions.py,
    where a short set silently ends the loop.
    """
    keys = set()
    for field in ("addressed", "deferred"):
        for record in entry.get(field) or []:
            if not isinstance(record, dict) or record.get("promoted_from") != "suggestion":
                continue
            if not well_formed_promotion(record):
                continue
            keys.add((record.get("file"), record.get("line"), base_summary(record["summary"])))
    return keys


def _candidates(entry: dict) -> list[dict]:
    """In-scope suggestions and nits this entry left open.

    out_of_scope findings are dropped: partition() routes them to deferred[],
    which the summary renders in its own section.
    """
    findings = entry.get("findings")
    if not isinstance(findings, list):
        return []
    settled = _settled(entry)
    out = []
    for f in findings:
        if not isinstance(f, dict) or not well_formed(f, owner_required=False):
            continue
        if f.get("severity") not in OPEN_SEVERITIES or f.get("scope") != "in_scope":
            continue
        if _key(f) in settled:
            continue
        out.append(f)
    return out


def _all_findings(entry: dict) -> list[dict]:
    findings = entry.get("findings")
    if not isinstance(findings, list):
        return []
    # owner_required=False: a finding is dropped here only for a shape the
    # matcher cannot read. `reviewer` is required of persisted findings but not
    # of synthesized ones, and rejecting one for its absence would lose it.
    return [f for f in findings if isinstance(f, dict) and well_formed(f, owner_required=False)]


def _ran(entry: dict) -> tuple[set[str], bool]:
    """(personas named as run, whether the whole panel ran) for one entry.

    Malformed or absent panel_selection reads as "nothing known to have run",
    which keeps earlier findings open. Fail-open is the right direction here:
    a stale bullet is noise the author can dismiss, while a dropped one is the
    bug this script exists to fix.

    `forced_full_sweep` is checked because panel_selection records the *initial*
    §4a.1 selection only; the pre-approval sweep runs personas it does not
    list (templates/state.schema.json, docs/delta-gate.md). It covers the panel,
    not the adversary, which is not a panel persona.

    Selection is not review. `panel_selection.ran` is written before the
    subagents produce anything, so a persona whose output failed validation
    (`reviewer_errors[]`, without a replacement response) or
    that came back shallow (`shallow_review[]`, approve with no evidence) is
    named there having decided nothing. Letting either resolve an earlier
    finding would retire it on a review that did not happen, which is why the
    same entry's `adversary_error` leaves `adversary` absent.
    """
    selection = entry.get("panel_selection")
    ran: set[str] = set()
    full = entry.get("forced_full_sweep") is True
    if isinstance(selection, dict):
        if selection.get("mode") == "full":
            full = True
        for name in selection.get("ran") or []:
            if isinstance(name, str):
                ran.add(name)
    if isinstance(entry.get(ADVERSARY), dict):
        ran.add(ADVERSARY)
    return ran, full


def _no_verdict(entry: dict) -> set[str]:
    """Personas that were selected but produced no usable review this iteration.

    legacy `shallow_blocker` and `adversary_shallow_giveup` records cannot
    settle earlier findings even when `adversary` is populated.
    """
    names = set()
    for record in entry.get("reviewer_errors") or []:
        if isinstance(record, dict) and isinstance(record.get("reviewer"), str):
            names.add(record["reviewer"])
    for name in entry.get("shallow_review") or []:
        if isinstance(name, str):
            names.add(name)
    adversary = entry.get(ADVERSARY)
    shallow_adversary = isinstance(adversary, dict) and adversary.get("shallow_blocker") is True
    if shallow_adversary or entry.get("adversary_shallow_giveup") is True:
        names.add(ADVERSARY)
    return names


def _owners_ran(item: dict, rnd: dict) -> bool:
    """Whether every persona that has ever raised this item reviewed again.

    Every, not any: §4c unions `source_reviewers` when two personas surface the
    same issue, and one of them going quiet is not the panel withdrawing it.
    An item whose owners cannot be determined is never settled this way; it can
    still be retired by a re-raise, a promotion or a deferral.

    Reads the item's accumulated owner set rather than its current finding's,
    because `source_reviewers` is per-iteration: `promote_findings.py` counts it
    within one call and never reads history[] (docs/synthesis.md). A
    delta-gated iteration that runs one of two co-owners therefore re-raises the
    finding with a *narrower* list, and taking the newest instance's list would
    let that persona alone retire what the panel co-owns.
    """
    if not item["owners"]:
        return False
    return all(_owner_ran(name, rnd) for name in item["owners"])


def _owner_ran(reviewer: str, rnd: dict) -> bool:
    if reviewer in rnd["no_verdict"]:
        # Checked ahead of full_panel: a sweep that ran every persona still did
        # not get a verdict out of this one.
        return False
    if reviewer == ADVERSARY:
        # The adversary runs on its own schedule (§4d.0), so a full panel sweep
        # says nothing about whether it looked again.
        return ADVERSARY in rnd["ran"]
    return rnd["full_panel"] or reviewer in rnd["ran"]


def _unmatched(findings: list[dict], previous: list[dict], rnd: dict) -> list[dict]:
    items = [{"finding": f, "owners": owners(f)} for f in findings]
    paired = _pair(items, previous, rnd)
    return [f for index, f in enumerate(findings) if index not in paired]


def _rounds(history: list, current: dict) -> list[dict]:
    """History entries oldest-first, with the current iteration folded in.

    The current iteration reaches Step 5 in one of two states: not yet in
    history[] (every exit before §4i), or in it from the §4d.1 SUCCESS path.
    Folding on the iteration number covers both. Older state records that
    SUCCESS entry with `findings: []`, which leaves the stdin partitions as the
    only record that iteration's panel produced anything at all.
    """
    rounds = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        iteration = entry.get("iteration")
        if not isinstance(iteration, int) or isinstance(iteration, bool):
            # Skipped whole, which does drop any findings it held: the one
            # place this module loses an item. There is no honest alternative:
            # the number is what orders the rounds and dates an item, and
            # `iteration` is required by templates/state.schema.json, so an
            # entry without one was not written by this loop.
            continue
        ran, full_panel = _ran(entry)
        rounds.append(
            {
                "iteration": iteration,
                "findings": _all_findings(entry),
                "candidates": _candidates(entry),
                "ran": ran,
                "full_panel": full_panel,
                "no_verdict": _no_verdict(entry),
            }
        )
    existing = next((r for r in rounds if r["iteration"] == current["iteration"]), None)
    if existing is None:
        rounds.append(current)
        # Sorted after appending, not before: a caller that legitimately passes a
        # number below the last persisted one (iteration 0 on a resume) must not
        # have its round processed as though it came last.
        rounds.sort(key=lambda r: r["iteration"])
        return rounds
    rounds.sort(key=lambda r: r["iteration"])
    # Union, not replacement. The stdin partitions are what an older-state §4d.1
    # SUCCESS entry lacks (its `findings: []` would otherwise read as "the full
    # panel ran and re-raised nothing" and resolve every carried item), but a caller
    # that passes nothing for an already-persisted iteration must not erase what
    # §4i wrote, which would be the same silent loss from the other direction.
    #
    # maximum matching keeps restatement order from duplicating a finding whose
    # only match a greedy pass gave to another item with alternatives.
    kept = _unmatched(current["candidates"], existing["candidates"], current)
    current_candidates = {id(f) for f in current["candidates"]}
    existing_candidates = {id(f) for f in existing["candidates"]}
    settlers = _unmatched(
        [f for f in current["findings"] if id(f) not in current_candidates],
        [f for f in existing["findings"] if id(f) not in existing_candidates],
        current,
    )
    # a duplicate settlement target would retire another nearby open finding.
    kept_ids = {id(f) for f in [*kept, *settlers]}
    existing["findings"] += [f for f in current["findings"] if id(f) in kept_ids]
    existing["candidates"] += kept
    existing["ran"] |= current["ran"]
    existing["full_panel"] = existing["full_panel"] or current["full_panel"]
    existing["no_verdict"] |= current["no_verdict"]
    return rounds


def _item(finding: dict, first_seen: int) -> dict:
    item = {}
    if finding.get("file") is not None:
        item["file"] = finding["file"]
    if finding.get("line") is not None:
        item["line"] = finding["line"]
    item["summary"] = finding.get("summary")
    item["first_seen_iteration"] = first_seen
    return item


def _rank(item: dict, finding: dict) -> tuple:
    """How well a round finding answers an open item. Higher sorts first.

    Only ever used to order candidate pairs that already match, so it ranks
    matches; it does not decide them. The §4c rule owns that.
    """
    distance = 0
    if item.get("line") is not None and finding.get("line") is not None:
        distance = abs(int(item["line"]) - int(finding["line"]))
    return (token_overlap(item.get("summary", ""), finding.get("summary", "")), -distance)


def _pair(items: list[dict], findings: list[dict], rnd: dict) -> dict[int, dict]:
    """Match open items to this round's findings, one finding per item.

    The ±5 line window is a window, not an equivalence relation: one re-raised
    finding can match two open items that do not match each other. Letting it
    answer for both retires an item nothing actually revisited (the silent drop
    this whole script exists to prevent), so each finding settles at most one
    item.

    Augmenting paths rather than a greedy sweep, for the reason
    `check_exit_conditions.py::_pairs_off` gives: matching is neither transitive
    nor injective, and a greedy pass can strand an item whose only match was
    taken by one that had alternatives. Stranding is not cosmetic here: an
    item whose owners all reviewed again is dropped when it goes unpaired.

    At-risk items are offered first for that reason: an item whose owner was
    skipped carries whether or not it pairs, so it must not take a finding an
    at-risk one needs. Maximum cardinality holds regardless of that order;
    the order decides *which* maximum matching, and this is the one that keeps
    the newer text on the item that has to survive on it.
    """
    prefs: dict[int, list[int]] = {}
    for ii, item in enumerate(items):
        matches = [fi for fi, f in enumerate(findings) if is_match_or_summary(item["finding"], f)]
        matches.sort(
            key=lambda fi: (
                -_rank(item["finding"], findings[fi])[0],
                -_rank(item["finding"], findings[fi])[1],
                fi,
            )
        )
        prefs[ii] = matches

    owner_of: dict[int, int] = {}

    def augment(ii: int, seen: set[int]) -> bool:
        for fi in prefs[ii]:
            if fi in seen:
                continue
            seen.add(fi)
            if fi not in owner_of or augment(owner_of[fi], seen):
                owner_of[fi] = ii
                return True
        return False

    at_risk = [_owners_ran(item, rnd) for item in items]
    for ii in sorted(range(len(items)), key=lambda ii: (not at_risk[ii], ii)):
        augment(ii, set())
    return {ii: findings[fi] for fi, ii in owner_of.items()}


def collect(current: dict, history: list) -> dict:
    """Walk the rounds oldest-first, carrying whatever no later round settled.

    An open item survives a later round unless that round re-raised it (the
    newer instance becomes canonical, and a blocker instance retires it from
    these sets), or ran its owning persona without re-raising it (the owner
    looked again and let it go). A round that skipped the owner decides
    nothing, which is the delta-gate case this exists for.
    """
    open_items: list[dict] = []
    rounds = _rounds(history, current)
    last_iteration = rounds[-1]["iteration"] if rounds else current["iteration"]
    for rnd in rounds:
        paired = _pair(open_items, rnd["findings"], rnd)
        surviving: list[dict] = []
        for index, entry in enumerate(open_items):
            match = paired.get(index)
            if match is not None:
                if not any(f is match for f in rnd["candidates"]):
                    # Promoted, deferred, or re-raised as a blocker: it has a
                    # section of its own now.
                    continue
                # Re-raised. Keep the newer text and location (the diff moved
                # on), but the first sighting is what dates the item.
                surviving.append(
                    {
                        "finding": match,
                        "first_seen": entry["first_seen"],
                        # Owners accumulate; they never narrow to the latest
                        # sighting's list. See _owners_ran.
                        "owners": entry["owners"] | owners(match),
                    }
                )
                continue
            if _owners_ran(entry, rnd):
                continue
            surviving.append(entry)

        for finding in rnd["candidates"]:
            if any(e["finding"] is finding for e in surviving):
                continue
            surviving.append(
                {
                    "finding": finding,
                    "first_seen": rnd["iteration"],
                    "owners": owners(finding),
                }
            )
        open_items = surviving

    partitions: dict[str, list[dict]] = {"suggestions": [], "nits": []}
    for entry in open_items:
        key = "nits" if entry["finding"].get("severity") == "nit" else "suggestions"
        partitions[key].append(_item(entry["finding"], entry["first_seen"]))
    for items in partitions.values():
        items.sort(key=lambda i: (i.get("file") or "", i.get("line") or 0, i["summary"]))
    return {
        **partitions,
        # Against the last round walked, not the number passed in: a resume can
        # legitimately pass an iteration below every persisted one.
        "carried": sum(
            1
            for items in partitions.values()
            for i in items
            if i["first_seen_iteration"] < last_iteration
        ),
    }


def _fail(message: str) -> int:
    print(f"collect_open_findings: {message}", file=sys.stderr)
    return 2


def _validate_findings(data: dict, key: str, *, needs_owner: bool = True) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        return f"{key} must be a list or null"
    for finding in value:
        if not isinstance(finding, dict):
            return f"every {key} entry must be an object"
        if not isinstance(finding.get("summary"), str):
            return f"every {key} entry needs a string 'summary'"
        if needs_owner and not isinstance(finding.get("source_reviewers", []), list):
            return f"every {key} entry's 'source_reviewers' must be a list"
        if finding.get("file") is not None and not isinstance(finding["file"], str):
            return f"every {key} entry's 'file' must be a string"
        line = finding.get("line")
        if line is not None and (not isinstance(line, int) or isinstance(line, bool)):
            return f"every {key} entry's 'line' must be an integer"
    return None


def _partition(findings: list, severity: str) -> list[dict]:
    """This iteration's items, tagged by the partition they arrived in.

    The array is authoritative, not the `severity` field: `partition()` routes
    on severity, but what Step 5 renders is the arrays, and an item that arrived
    in `nits[]` must not come back out under Suggestions because its field went
    missing in transit. out_of_scope items are dropped for the same reason the
    history filter drops them: `deferred[]` owns that section.
    """
    return [{**f, "severity": severity} for f in findings if f.get("scope") != "out_of_scope"]


def _current_round(data: dict) -> dict:
    suggestions = _partition(data.get("suggestions") or [], "suggestion")
    nits = _partition(data.get("nits") or [], "nit")
    blockers = data.get("blockers") or []
    deferred = [f for f in _all_findings(data) if f.get("scope") == "out_of_scope"]
    deferred.extend(
        {**record, "summary": base_summary(record["summary"])}
        for record in data.get("deferred") or []
        if isinstance(record, dict) and well_formed_promotion(record)
    )
    ran = {name for name in data.get("panel_ran") or [] if isinstance(name, str)}
    if isinstance(data.get(ADVERSARY), dict):
        # §4d.0 runs before MAX_ITERATIONS and the approval exit, so the
        # adversary can have reviewed this iteration. It is not a panel persona
        # and never appears in panel_ran.
        ran.add(ADVERSARY)
    return {
        "iteration": data["iteration"],
        # blockers and deferrals settle earlier items without entering the open sets.
        "findings": [*blockers, *deferred, *suggestions, *nits],
        "candidates": [*suggestions, *nits],
        "ran": ran,
        "full_panel": data.get("forced_full_sweep") is True,
        # Same rule the history path applies, over the same two fields: this
        # iteration is not in history[] on any exit before §4i, so without them
        # a persona that errored or reviewed shallowly would be read straight
        # off panel_ran as having looked again.
        "no_verdict": _no_verdict(data),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect still-open suggestions and nits.")
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return _fail(f"stdin is not valid JSON: {e}")
    if not isinstance(data, dict):
        return _fail("stdin must be a JSON object")

    iteration = data.get("iteration")
    if not isinstance(iteration, int) or isinstance(iteration, bool) or iteration < 0:
        # 0 is legal and means "no iteration has run": EXTERNAL_PUSH from §3.6
        # and SCOPE_SPLIT_RECOMMENDED from Step 3.5 both post a comment before
        # the loop starts. There is nothing to accumulate, and the honest answer
        # is empty sets rather than the exit-2 that would leave Step 5 with no
        # sections at all.
        return _fail("iteration must be an integer >= 0")
    for key in ("suggestions", "nits"):
        error = _validate_findings(data, key)
        if error:
            return _fail(error)
    # Blockers are match targets only and never carry, so their owner is never
    # read. §4d.2's synthetic CI blockers do carry `reviewer: "ci"`
    # (docs/ci-conversion.md); the exemption is about what this script uses, not
    # about what they have.
    for key in ("blockers", "findings"):
        error = _validate_findings(data, key, needs_owner=False)
        if error:
            return _fail(error)
    for key in ("panel_ran", "shallow_review", "reviewer_errors"):
        if data.get(key) is not None and not isinstance(data[key], list):
            return _fail(f"{key} must be a list or null")
    if data.get(ADVERSARY) is not None and not isinstance(data[ADVERSARY], dict):
        return _fail("adversary must be an object or null")
    if data.get("forced_full_sweep") is not None and not isinstance(
        data["forced_full_sweep"], bool
    ):
        return _fail("forced_full_sweep must be a boolean or null")

    try:
        state = load_state(args.state)
    except StateValidationError as e:
        return _fail(str(e))
    history = state.get("history")
    if not isinstance(history, list):
        history = []

    json.dump(collect(_current_round(data), history), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
