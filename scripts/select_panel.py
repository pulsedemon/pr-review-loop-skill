#!/usr/bin/env python3
# select_panel.py: decide which reviewer personas run this iteration.
#
# Implements the delta-gated panel selection described in
# docs/delta-gate.md. The orchestrator calls this once per iteration after
# the §4a.1 gate pre-pass (if any) and before the §4b fan-out.
#
# stdin: {
#   panel: [str],                  effective panel after approvers_required
#   iteration: int,                1-based
#   delta_gate: bool,              master switch
#   delta_gate_min_candidates: int cap below which the gate is skipped
#   prev_history: object|null      history[] entry of iteration N-1 (null at N=1)
#   gate_results: [object]         validated gate outputs for candidates
# }
# stdout: panel_selection object (see docs/delta-gate.md).
#
# exit codes:
#   0: emitted a panel_selection
#   2: usage / malformed input

import json
import sys

from finding_contract import is_open_blocker, promoted_keys

REQUIRED = ("panel", "iteration", "delta_gate", "delta_gate_min_candidates")


def _full(panel: list) -> dict:
    return {
        "mode": "full",
        "ran": list(panel),
        "skipped": [],
        "gate_relevant": [],
        "gate_fail_open": [],
        "open_blocker_carryover": [],
    }


def _usable_prev_history(prev_history: dict | None) -> bool:
    return isinstance(prev_history, dict) and isinstance(prev_history.get("findings"), list)


def _open_blocker_personas(prev_history: dict | None, panel: list) -> list:
    """Personas that owned an open (not deferred) blocker in history[N-1].

    Owners are `source_reviewers` plus the singular `reviewer` that
    templates/state.schema.json requires on a persisted finding. Read both so
    a blocker never loses an owner: a blocker cannot vanish via skipping.
    """
    if not _usable_prev_history(prev_history):
        return []
    promoted = promoted_keys(prev_history)
    if promoted is None:
        return list(panel)
    panel_set = set(panel)
    out = []
    for finding in prev_history.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        if not is_open_blocker(finding, promoted):
            continue
        owners = list(finding.get("source_reviewers") or [])
        reviewer = finding.get("reviewer")
        if isinstance(reviewer, str):
            owners.append(reviewer)
        for src in owners:
            if src in panel_set and src not in out:
                out.append(src)
    return [p for p in panel if p in out]  # panel order, stable


def select(data: dict) -> dict:
    panel = data["panel"]
    if data["iteration"] <= 1 or not data["delta_gate"]:
        return _full(panel)

    prev_history = data.get("prev_history")
    if not _usable_prev_history(prev_history):
        # The carryover contract is safety-critical: if the caller fails to pass a
        # usable history[N-1] entry, run the full panel rather than risk skipping
        # a persona that still owns an open blocker.
        return _full(panel)

    carryover = _open_blocker_personas(prev_history, panel)
    carry_set = set(carryover)
    candidates = [p for p in panel if p not in carry_set]

    gate_relevant: list[str] = []
    gate_fail_open: list[str] = []

    if len(candidates) < data["delta_gate_min_candidates"]:
        # Below the cap: the gate is not worth running; every persona runs.
        ran = list(panel)
    else:
        verdicts = {
            g["reviewer"]: g["relevant"]
            for g in data.get("gate_results") or []
            if isinstance(g, dict) and "reviewer" in g and "relevant" in g
        }
        ran = list(carryover)
        for c in candidates:
            if c not in verdicts:
                gate_fail_open.append(c)  # fail-open: no trustworthy verdict
                ran.append(c)
            elif verdicts[c]:
                gate_relevant.append(c)
                ran.append(c)
            # verdicts[c] is False => skipped
        ran = [p for p in panel if p in set(ran)]  # panel order, stable

    skipped = [p for p in panel if p not in set(ran)]
    return {
        "mode": "full" if not skipped else "delta_gated",
        "ran": ran,
        "skipped": skipped,
        "gate_relevant": [p for p in panel if p in set(gate_relevant)],
        "gate_fail_open": [p for p in panel if p in set(gate_fail_open)],
        "open_blocker_carryover": list(carryover),
    }


def main() -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"select_panel: stdin is not valid JSON ({exc})", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("select_panel: stdin must be a JSON object", file=sys.stderr)
        return 2
    for key in REQUIRED:
        if key not in data:
            print(f"select_panel: missing required key `{key}`", file=sys.stderr)
            return 2
    if not isinstance(data["panel"], list) or not data["panel"]:
        print("select_panel: `panel` must be a non-empty array", file=sys.stderr)
        return 2
    if any(not isinstance(name, str) for name in data["panel"]):
        print("select_panel: `panel` entries must be strings", file=sys.stderr)
        return 2
    if len(data["panel"]) != len(set(data["panel"])):
        print("select_panel: `panel` must not contain duplicate persona names", file=sys.stderr)
        return 2
    # bool is an int subclass; reject it explicitly so `iteration`/
    # `delta_gate_min_candidates` cannot be satisfied by `true`/`false`.
    if not isinstance(data["iteration"], int) or isinstance(data["iteration"], bool):
        print("select_panel: `iteration` must be an integer", file=sys.stderr)
        return 2
    if not isinstance(data["delta_gate"], bool):
        print("select_panel: `delta_gate` must be a boolean", file=sys.stderr)
        return 2
    if not isinstance(data["delta_gate_min_candidates"], int) or isinstance(
        data["delta_gate_min_candidates"], bool
    ):
        print("select_panel: `delta_gate_min_candidates` must be an integer", file=sys.stderr)
        return 2

    json.dump(select(data), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
