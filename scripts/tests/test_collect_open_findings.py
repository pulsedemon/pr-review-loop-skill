"""Unit tests for scripts/collect_open_findings.py.

The behavior under test is the resolution rule documented in
docs/step5-summary.md: a suggestion or nit raised in an early iteration stays
open until a later iteration settles it, and a delta-gated skip settles
nothing.
"""

import json
import subprocess
import sys
from pathlib import Path

import collect_open_findings as cof
import pytest
from finding_contract import annotate_evidence_failure

SCRIPT = Path(__file__).resolve().parents[1] / "collect_open_findings.py"


def finding(reviewer="tests", severity="suggestion", *, file="src/a.py", line=10, summary=None):
    return {
        "reviewer": reviewer,
        "source_reviewers": [reviewer],
        "severity": severity,
        "scope": "in_scope",
        "file": file,
        "line": line,
        "summary": summary or f"{reviewer} finding about the parser cache invalidation path",
    }


def entry(iteration, *, findings=(), ran=("tests",), mode="delta_gated", **extra):
    record = {
        "iteration": iteration,
        "head_sha_before": "a" * 40,
        "head_sha_after": "b" * 40,
        "ci_status": "skipped",
        "findings": list(findings),
        "panel_selection": {
            "mode": mode,
            "ran": list(ran),
            "skipped": [],
            "gate_relevant": [],
            "gate_fail_open": [],
            "open_blocker_carryover": [],
        },
    }
    record.update(extra)
    return record


def current(iteration, *, suggestions=(), nits=(), blockers=(), ran=(), full_sweep=False, **extra):
    payload = {
        "iteration": iteration,
        "suggestions": list(suggestions),
        "nits": list(nits),
        "blockers": list(blockers),
        "panel_ran": list(ran),
        "forced_full_sweep": full_sweep,
    }
    payload.update(extra)
    return payload


def collect(payload, history):
    return cof.collect(cof._current_round(payload), history)


def summaries(items):
    return [i["summary"] for i in items]


def test_skipped_owner_carries_the_earlier_finding():
    f = finding(severity="nit")
    history = [entry(1, findings=[f], ran=["tests"])]
    # iteration 2's delta-gated panel skipped `tests`, so nothing revisited it.
    result = collect(current(2, ran=["correctness"]), history)
    assert summaries(result["nits"]) == [f["summary"]]
    assert result["nits"][0]["first_seen_iteration"] == 1
    assert result["carried"] == 1


def test_owner_that_ran_again_without_re_raising_resolves_it():
    history = [entry(1, findings=[finding()], ran=["tests"])]
    result = collect(current(2, ran=["tests"]), history)
    assert result["suggestions"] == []
    assert result["carried"] == 0


def test_forced_full_sweep_resolves_a_finding_no_persona_re_raised():
    history = [
        entry(1, findings=[finding()], ran=["tests"]),
        entry(2, findings=[], ran=["correctness"], forced_full_sweep=True),
    ]
    assert collect(current(3, ran=["correctness"]), history)["suggestions"] == []


def test_full_mode_panel_resolves_it_too():
    history = [entry(1, findings=[finding()], ran=["tests"])]
    result = collect(current(2, ran=[], full_sweep=True), history)
    assert result["suggestions"] == []


def test_re_raised_finding_renders_once_dated_to_its_first_sighting():
    f = finding()
    history = [
        entry(1, findings=[f], ran=["tests"]),
        entry(2, findings=[dict(f, line=12)], ran=["tests"]),
    ]
    result = collect(current(3, ran=["correctness"]), history)
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["first_seen_iteration"] == 1
    # The newer instance is canonical: the diff moved, so the line did too.
    assert result["suggestions"][0]["line"] == 12


def test_a_later_blocker_instance_retires_the_suggestion():
    f = finding()
    history = [
        entry(1, findings=[f], ran=["tests"]),
        entry(2, findings=[dict(f, severity="blocker")], ran=["tests"]),
    ]
    assert collect(current(3, ran=[]), history)["suggestions"] == []


def test_this_iterations_blockers_retire_an_earlier_suggestion():
    # Otherwise the same issue renders under Outstanding blockers *and* as an
    # open suggestion in the same comment.
    f = finding()
    history = [entry(1, findings=[f], ran=["tests"])]
    payload = current(2, blockers=[dict(f, severity="blocker")], ran=[])
    assert collect(payload, history)["suggestions"] == []


def test_promotion_in_the_same_iteration_is_not_an_open_suggestion():
    f = finding()
    promoted = entry(1, findings=[f], ran=["tests"])
    promoted["addressed"] = [
        {
            "file": f["file"],
            "line": f["line"],
            "summary": f["summary"],
            "promoted_from": "suggestion",
            "promoted_by": "multi-persona",
            "promotion_reason": "multi_source",
            "source_reviewers": ["tests", "correctness"],
        }
    ]
    assert collect(current(2, ran=[]), [promoted])["suggestions"] == []


def test_evidence_verification_failure_stays_in_deferred():
    # The record carries the annotated summary promote_findings.py actually
    # writes, not the finding's own: comparing on raw equality here would pass
    # while the real record rendered under Deferred *and* as an open suggestion.
    f = finding(reviewer="adversary")
    deferred = entry(1, findings=[f], ran=["tests"])
    deferred["deferred"] = [
        {
            "file": f["file"],
            "line": f["line"],
            "summary": annotate_evidence_failure(f["summary"], "line 10 out of range"),
            "promoted_from": "suggestion",
            "promoted_by": "adversary",
            "promotion_reason": "evidence_verification_failed",
            "source_reviewers": ["adversary"],
        }
    ]
    assert collect(current(2, ran=[]), [deferred])["suggestions"] == []


def test_a_re_raise_settles_one_item_not_every_item_it_matches():
    # The ±5 window is not an equivalence relation: X at 10 and Y at 20 do not
    # match each other, but Z at 15 matches both. Letting Z answer for both
    # retires an item nothing revisited, the silent drop this script exists to
    # prevent. Same hazard check_exit_conditions.py::_pairs_off documents.
    same = "the tenant id is missing from the cache key"
    history = [
        entry(1, findings=[finding(line=10, summary=same)], ran=["tests"]),
        entry(2, findings=[finding("correctness", line=20, summary=same)], ran=["correctness"]),
        entry(3, findings=[finding(line=15, summary=same)], ran=["tests"]),
    ]
    result = collect(current(4, ran=[]), history)
    # Z claims the `tests` item; `correctness` never ran again, so its own stays.
    assert [(i["line"], i["first_seen_iteration"]) for i in result["suggestions"]] == [
        (15, 1),
        (20, 2),
    ]


def test_a_persona_whose_review_errored_did_not_look_again():
    # panel_selection.ran is written before the subagents produce anything, so a
    # persona in reviewer_errors[] is named there having decided nothing.
    f = finding()
    history = [
        entry(1, findings=[f], ran=["tests"]),
        entry(2, findings=[], ran=["tests"], reviewer_errors=[{"reviewer": "tests", "error": "x"}]),
    ]
    assert summaries(collect(current(3, ran=[]), history)["suggestions"]) == [f["summary"]]


def test_a_shallow_review_does_not_resolve_an_earlier_finding():
    f = finding()
    history = [
        entry(1, findings=[f], ran=["tests"]),
        entry(2, findings=[], ran=["tests"], shallow_review=["tests"]),
    ]
    assert summaries(collect(current(3, ran=[]), history)["suggestions"]) == [f["summary"]]


def test_a_full_sweep_does_not_speak_for_a_persona_that_errored_in_it():
    f = finding()
    history = [
        entry(1, findings=[f], ran=["tests"]),
        entry(
            2,
            findings=[],
            ran=[],
            forced_full_sweep=True,
            reviewer_errors=[{"reviewer": "tests", "error": "schema invalid"}],
        ),
    ]
    assert summaries(collect(current(3, ran=[]), history)["suggestions"]) == [f["summary"]]


def test_out_of_scope_findings_are_left_to_the_deferred_section():
    f = dict(finding(), scope="out_of_scope")
    assert collect(current(2, ran=[]), [entry(1, findings=[f])])["suggestions"] == []


def test_a_full_panel_sweep_does_not_speak_for_the_adversary():
    f = finding(reviewer="adversary")
    history = [entry(1, findings=[f], ran=["tests"], adversary={"verdict": "comment"})]
    result = collect(current(2, ran=[], full_sweep=True), history)
    assert summaries(result["suggestions"]) == [f["summary"]]


def test_an_adversary_re_run_that_drops_it_resolves_it():
    f = finding(reviewer="adversary")
    history = [
        entry(1, findings=[f], ran=["tests"], adversary={"verdict": "comment"}),
        entry(2, findings=[], ran=["tests"], adversary={"verdict": "approve"}),
    ]
    assert collect(current(3, ran=[]), history)["suggestions"] == []


def test_success_path_entry_folds_in_this_iterations_partitions():
    # Older state records the §4d.1 approving entry with `findings: []`, so history
    # alone reads as "the full panel ran and re-raised nothing". Folding the stdin
    # partitions onto that entry, rather than treating them as a later round, is
    # what keeps a re-raised item dated to its first sighting.
    f = finding(severity="nit")
    history = [
        entry(1, findings=[f], ran=["tests"]),
        entry(2, findings=[], ran=["tests"], mode="full"),
    ]
    result = collect(current(2, nits=[f], ran=["tests"], full_sweep=True), history)
    assert summaries(result["nits"]) == [f["summary"]]
    assert result["nits"][0]["first_seen_iteration"] == 1
    assert result["carried"] == 1


def test_folding_never_erases_what_this_iteration_already_persisted():
    # A caller that passes empty partitions for an iteration §4i already wrote
    # must not lose that iteration's findings: replacement rather than union
    # would drop them, which is the same silent loss from the other direction.
    f = finding()
    history = [entry(2, findings=[f], ran=["tests"])]
    result = collect(current(2, ran=["tests"]), history)
    assert summaries(result["suggestions"]) == [f["summary"]]


@pytest.mark.parametrize(
    "restated",
    [
        pytest.param({}, id="byte-identical"),
        pytest.param({"line": 12}, id="moved-two-lines"),
        pytest.param(
            {"summary": "tests finding about the parser cache invalidation paths"},
            id="one-word-off",
        ),
    ],
)
def test_folding_does_not_double_an_item_passed_on_both_sides(restated):
    # A host re-reading a moved diff restates the same finding a line or a word
    # over. Exact-key de-duplication here would render both bullets.
    f = finding()
    history = [entry(2, findings=[f], ran=["tests"])]
    result = collect(current(2, suggestions=[dict(f, **restated)], ran=["tests"]), history)
    assert len(result["suggestions"]) == 1


def test_a_skipped_owner_carries_across_an_already_persisted_iteration():
    # The delta-gate case on a terminal exit that ran §4i first: iteration 2 is
    # in history[] and never ran `tests`, so its nit is still open at Step 5.
    carried = finding(severity="nit", file="src/b.py")
    fresh = finding(reviewer="comments", file="src/c.py")
    history = [
        entry(1, findings=[carried], ran=["tests"]),
        entry(2, findings=[], ran=["comments"]),
    ]
    result = collect(current(3, suggestions=[fresh], ran=["comments"]), history)
    assert summaries(result["nits"]) == [carried["summary"]]
    assert summaries(result["suggestions"]) == [fresh["summary"]]
    assert result["carried"] == 1


def test_reviewer_never_reaches_the_renderer():
    history = [entry(1, findings=[finding()], ran=["tests"])]
    result = collect(current(2, ran=[]), history)
    assert "reviewer" not in result["suggestions"][0]
    assert set(result["suggestions"][0]) == {"file", "line", "summary", "first_seen_iteration"}


def test_items_sort_by_file_then_line():
    history = [
        entry(
            1,
            findings=[
                finding(file="src/z.py", line=3, summary="z file suggestion about retry budget"),
                finding(file="src/a.py", line=90, summary="a file suggestion about retry budget"),
                finding(file="src/a.py", line=9, summary="another a file note on retry budget"),
            ],
            ran=["tests"],
        )
    ]
    result = collect(current(2, ran=[]), history)
    assert [(i["file"], i["line"]) for i in result["suggestions"]] == [
        ("src/a.py", 9),
        ("src/a.py", 90),
        ("src/z.py", 3),
    ]


def test_the_partition_an_item_arrives_in_decides_where_it_renders():
    # Not its `severity` field: what Step 5 renders is the arrays. A suggestion
    # handed to nits[] renders as a nit, and a field lost in transit changes
    # nothing.
    result = collect(current(2, nits=[finding(severity="suggestion")], ran=[]), [])
    assert len(result["nits"]) == 1
    assert result["suggestions"] == []
    stray = {"source_reviewers": ["tests"], "summary": "no severity", "file": "a.py", "line": 1}
    assert len(collect(current(2, nits=[stray], ran=[]), [])["nits"]) == 1


def test_an_out_of_scope_item_passed_on_stdin_is_left_to_deferred():
    f = dict(finding(), scope="out_of_scope")
    assert collect(current(2, suggestions=[f], ran=[]), [])["suggestions"] == []


def test_an_absent_panel_selection_settles_nothing():
    # Fail-open: a stale bullet is noise, a dropped one is the bug.
    f = finding()
    history = [entry(1, findings=[f], ran=["tests"]), {"iteration": 2, "findings": []}]
    assert summaries(collect(current(3, ran=[]), history)["suggestions"]) == [f["summary"]]


def test_a_malformed_ran_list_names_nobody():
    f = finding()
    broken = {"iteration": 2, "findings": [], "panel_selection": {"mode": "delta_gated", "ran": {}}}
    history = [entry(1, findings=[f], ran=["tests"]), broken]
    assert summaries(collect(current(3, ran=[]), history)["suggestions"]) == [f["summary"]]


def test_an_errored_adversary_did_not_look_again():
    f = finding(reviewer="adversary")
    history = [
        entry(1, findings=[f], ran=["tests"], adversary={"verdict": "comment"}),
        entry(2, findings=[], ran=["tests"], adversary_error="schema invalid"),
    ]
    assert summaries(collect(current(3, ran=[]), history)["suggestions"]) == [f["summary"]]


def test_a_malformed_provenance_record_settles_nothing_rather_than_the_entry():
    # The documented divergence from check_exit_conditions.py: skipping one bad
    # record costs a duplicated bullet, dropping the entry costs every finding
    # on it.
    f = finding()
    e = entry(1, findings=[f], ran=["tests"])
    e["addressed"] = [{"promoted_from": "suggestion", "summary": None}]
    assert summaries(collect(current(2, ran=[]), [e])["suggestions"]) == [f["summary"]]


def test_malformed_history_entry_does_not_lose_the_rest():
    history = ["not an entry", entry(1, findings=[finding()], ran=["tests"])]
    assert len(collect(current(2, ran=[]), history)["suggestions"]) == 1


def test_unlocated_findings_match_on_exact_summary():
    f = {"reviewer": "tests", "severity": "nit", "scope": "in_scope", "summary": "flaky sleep"}
    history = [entry(1, findings=[f], ran=["tests"]), entry(2, findings=[dict(f)], ran=["tests"])]
    result = collect(current(3, ran=[]), history)
    assert len(result["nits"]) == 1
    assert "file" not in result["nits"][0]


def fixed(f):
    return {
        "file": f["file"],
        "line": f["line"],
        "summary": f["summary"],
        "fixed_from": f["severity"],
    }


def test_a_fixed_nit_settles_and_its_unfixed_neighbor_carries():
    # the neighbor sits within the matcher's window and overlaps its summary, so
    # a fuzzy settlement would retire it too
    done = finding(severity="nit", line=10, summary="typo in the retry budget comment")
    left = finding(severity="nit", line=13, summary="typo in the retry budget comment header")
    e = entry(1, findings=[done, left], ran=["tests"], addressed=[fixed(done)])
    result = collect(current(2, ran=["correctness"]), [e])
    assert summaries(result["nits"]) == [left["summary"]]


def test_a_fixed_nit_stays_settled_when_its_iteration_is_folded_in():
    # the Step 5 caller passes an appended iteration's partitions verbatim, fixed nit included
    f = finding(severity="nit")
    e = entry(1, findings=[f], ran=["tests"], addressed=[fixed(f)])
    assert collect(current(1, nits=[dict(f)], ran=["tests"]), [e])["nits"] == []


@pytest.mark.parametrize(
    "bad",
    [{"fixed_from": "blocker"}, {"summary": ["typo"]}, {"line": True}],
    ids=["not-an-open-severity", "list-summary", "bool-line"],
)
def test_a_malformed_fixed_record_settles_nothing(bad):
    # line 1, so a bool line would key-equal the finding without the type check
    f = finding(severity="nit", line=1)
    e = entry(1, findings=[f], ran=["tests"], addressed=[{**fixed(f), **bad}])
    assert summaries(collect(current(2, ran=[]), [e])["nits"]) == [f["summary"]]


def test_an_unlocated_fixed_record_settles_an_unlocated_nit():
    f = {"reviewer": "tests", "severity": "nit", "scope": "in_scope", "summary": "flaky sleep"}
    e = entry(
        1, findings=[f], ran=["tests"], addressed=[{"summary": f["summary"], "fixed_from": "nit"}]
    )
    assert collect(current(2, ran=[]), [e])["nits"] == []


def test_a_fix_settles_the_earlier_sighting_it_re_raised():
    # iteration 2 re-raises it from another persona, so the owner `tests` never
    # runs again and only pairing with the fixed instance can retire iteration 1's
    f = finding()
    g = dict(f, reviewer="correctness", source_reviewers=["correctness"])
    history = [
        entry(1, findings=[f], ran=["tests"]),
        entry(2, findings=[g], ran=["correctness"], addressed=[fixed(g)]),
    ]
    assert collect(current(3, ran=["correctness"]), history)["suggestions"] == []


def test_a_nit_re_raised_after_its_fix_is_open_again():
    f = finding(severity="nit")
    history = [entry(1, findings=[f], ran=["tests"], addressed=[fixed(f)])]
    result = collect(current(2, nits=[f], ran=["tests"]), history)
    assert summaries(result["nits"]) == [f["summary"]]
    assert result["nits"][0]["first_seen_iteration"] == 2


def run_cli(payload, state, extra_args=()):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--state", str(state), *extra_args],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


@pytest.fixture
def state_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"iteration": 1, "history": [entry(1, findings=[finding()])]}))
    return path


def test_cli_emits_the_open_sets(state_file):
    proc = run_cli(current(2, ran=[]), state_file)
    assert proc.returncode == 0, proc.stderr
    assert len(json.loads(proc.stdout)["suggestions"]) == 1


def test_cli_accepts_a_blocker_with_no_owner(state_file):
    # §4d.2 converts a failed CI check into a synthetic blocker; there is no
    # persona behind it. Rejecting one would cost Step 5 the whole open set on
    # exactly the runs most likely to have carried findings.
    ci_blocker = {"summary": "the build check failed", "file": "src/a.py", "line": 10}
    proc = run_cli(current(2, blockers=[ci_blocker], ran=[]), state_file)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize(
    "payload",
    [
        {"suggestions": []},
        {"iteration": -1},
        {"iteration": True},
        {"iteration": 2, "suggestions": "x"},
        {"iteration": 2, "suggestions": [{"reviewer": "tests"}]},
        {"iteration": 2, "nits": [{"summary": "s", "source_reviewers": "tests"}]},
        {"iteration": 2, "blockers": [{"reviewer": "tests", "summary": "s", "line": True}]},
        {"iteration": 2, "panel_ran": "tests"},
        {"iteration": 2, "shallow_review": "tests"},
        {"iteration": 2, "reviewer_errors": {}},
        {"iteration": 2, "forced_full_sweep": "true"},
    ],
)
def test_cli_rejects_malformed_input(payload, state_file):
    proc = run_cli(payload, state_file)
    assert proc.returncode == 2
    assert "collect_open_findings:" in proc.stderr


def test_cli_rejects_a_missing_state_file(tmp_path):
    proc = run_cli(current(2), tmp_path / "nope.json")
    assert proc.returncode == 2


def test_cli_rejects_non_object_stdin(state_file):
    proc = run_cli([], state_file)
    assert proc.returncode == 2


def test_well_formed_defaults_to_requiring_an_owner():
    # check_exit_conditions.py relies on the default: a persisted finding with no
    # `reviewer` makes the whole entry untrusted, so NO_PROGRESS cannot fire off
    # a blocker set reconstructed from partial data. This collector is the caller
    # that opts out, and nothing else should inherit that.
    import finding_contract

    ownerless = {"summary": "s", "severity": "blocker", "scope": "in_scope"}
    assert not finding_contract.well_formed(ownerless)
    assert finding_contract.well_formed(ownerless, owner_required=False)
    assert finding_contract.well_formed(dict(ownerless, reviewer="tests"))


def test_a_synthesized_finding_is_owned_by_its_source_reviewers():
    # reviewers/output.schema.json puts `reviewer` at the response level with
    # additionalProperties:false on each finding, so a finding coming out of
    # promote_findings.py has no `reviewer` at all, only source_reviewers.
    f = {
        "source_reviewers": ["tests"],
        "severity": "suggestion",
        "scope": "in_scope",
        "file": "src/a.py",
        "line": 10,
        "summary": "the fixture is shared across two tests that both mutate it",
    }
    history = [entry(1, findings=[f], ran=["tests"])]
    assert len(collect(current(2, ran=["correctness"]), history)["suggestions"]) == 1
    assert collect(current(2, ran=["tests"]), history)["suggestions"] == []


def test_every_owner_must_have_looked_again():
    # §4c unions source_reviewers when two personas surface the same issue; one
    # of them going quiet is not the panel withdrawing it.
    f = dict(finding(), source_reviewers=["tests", "correctness"])
    history = [entry(1, findings=[f], ran=["tests", "correctness"])]
    assert len(collect(current(2, ran=["tests"]), history)["suggestions"]) == 1
    assert collect(current(2, ran=["tests", "correctness"]), history)["suggestions"] == []


def test_an_ownerless_finding_is_never_settled_by_the_owner_test():
    f = {k: v for k, v in finding().items() if k not in ("reviewer", "source_reviewers")}
    history = [entry(1, findings=[f], ran=["tests"])]
    assert len(collect(current(2, ran=["tests"], full_sweep=True), history)["suggestions"]) == 1
    # ...but a re-raise as a blocker still retires it.
    payload = current(2, blockers=[dict(f, severity="blocker")], ran=["tests"])
    assert collect(payload, history)["suggestions"] == []


def test_this_iterations_errored_and_shallow_personas_did_not_look():
    # Every status that motivates this script exits before §4i, so the current
    # iteration's reviewer_errors[]/shallow_review[] exist only on stdin.
    f = finding()
    history = [entry(1, findings=[f], ran=["tests"])]
    assert collect(current(2, ran=["tests"]), history)["suggestions"] == []
    errored = current(2, ran=["tests"], reviewer_errors=[{"reviewer": "tests", "error": "x"}])
    assert len(collect(errored, history)["suggestions"]) == 1
    shallow = current(2, ran=["tests"], shallow_review=["tests"])
    assert len(collect(shallow, history)["suggestions"]) == 1


@pytest.mark.parametrize(
    "shallow_state",
    [
        pytest.param({"adversary": {"verdict": "approve", "shallow_blocker": True}}, id="blocker"),
        pytest.param(
            {"adversary": {"verdict": "approve"}, "adversary_shallow_giveup": True}, id="giveup"
        ),
    ],
)
def test_a_shallow_adversary_did_not_look_again(shallow_state):
    # docs/adversary.md's two shallow states both leave history[].adversary
    # populated, which would otherwise read as "the adversary reviewed again".
    f = finding(reviewer="adversary")
    history = [
        entry(1, findings=[f], ran=["tests"], adversary={"verdict": "comment", "findings": []}),
        entry(2, findings=[], ran=["tests"], **shallow_state),
    ]
    assert summaries(collect(current(3, ran=[]), history)["suggestions"]) == [f["summary"]]


def test_a_promotion_does_not_retire_a_different_finding_five_lines_away():
    # _settled compares keys, not the §4c window: _provenance copies file/line/
    # summary verbatim, and a fuzzy check here would drop a distinct nit that
    # then renders in no section at all.
    promoted = finding("security", line=10, summary="the token is logged in plaintext on failure")
    nearby = finding("comments", "nit", line=12, summary="the token is logged in plaintext today")
    e = entry(1, findings=[promoted, nearby], ran=["security", "comments"])
    e["addressed"] = [
        {
            "file": promoted["file"],
            "line": promoted["line"],
            "summary": promoted["summary"],
            "promoted_from": "suggestion",
            "promoted_by": "multi-persona",
            "promotion_reason": "multi_source",
            "source_reviewers": ["security", "correctness"],
        }
    ]
    result = collect(current(2, ran=[]), [e])
    assert summaries(result["nits"]) == [nearby["summary"]]
    assert result["suggestions"] == []


def test_a_folded_away_duplicate_cannot_retire_an_unrelated_item():
    # Dropping the duplicate from candidates[] but leaving it in findings[] lets
    # it pair with some other open item and retire it as promoted-or-deferred.
    same = "the tenant id is missing from the cache key"
    history = [
        entry(1, findings=[finding(line=10, summary=same)], ran=["tests"]),
        entry(2, findings=[finding("correctness", line=20, summary=same)], ran=["correctness"]),
    ]
    payload = current(2, suggestions=[finding("correctness", line=15, summary=same)], ran=[])
    result = collect(payload, history)
    assert [(i["line"], i["first_seen_iteration"]) for i in result["suggestions"]] == [
        (10, 1),
        (20, 2),
    ]


def test_pairing_prefers_the_item_that_would_otherwise_be_dropped():
    # Two isomorphic histories differing only in which item was seen first must
    # keep the same number of items: an unpaired item whose owner reviewed again
    # is dropped, so the safe item must not claim the finding.
    same = "the tenant id is missing from the cache key"
    x = finding("tests", line=10, summary=same)
    y = finding("correctness", line=18, summary=same)
    z = finding("correctness", line=14, summary=same)
    first = [
        entry(1, findings=[x], ran=["tests"]),
        entry(2, findings=[y], ran=["correctness"]),
        entry(3, findings=[z], ran=["correctness"]),
    ]
    second = [
        entry(1, findings=[y], ran=["correctness"]),
        entry(2, findings=[x], ran=["tests"]),
        entry(3, findings=[z], ran=["correctness"]),
    ]
    assert len(collect(current(4, ran=[]), first)["suggestions"]) == 2
    assert len(collect(current(4, ran=[]), second)["suggestions"]) == 2


def test_an_annotated_reason_containing_a_newline_still_strips():
    # _verify_evidence interpolates un-repr'd strings from LLM JSON.
    f = finding(reviewer="adversary")
    reason = "symbol 'def handle(\n  self)' not present in src/a.py"
    deferred = entry(1, findings=[f], ran=["tests"])
    deferred["deferred"] = [
        {
            "file": f["file"],
            "line": f["line"],
            "summary": annotate_evidence_failure(f["summary"], reason),
            "promoted_from": "suggestion",
            "promoted_by": "adversary",
            "promotion_reason": "evidence_verification_failed",
            "source_reviewers": ["adversary"],
        }
    ]
    assert collect(current(2, ran=[]), [deferred])["suggestions"] == []


def test_iteration_zero_is_legal_and_empty(tmp_path):
    # EXTERNAL_PUSH from §3.6 and SCOPE_SPLIT_RECOMMENDED from Step 3.5 both
    # post a comment before any iteration ran, so history[] is empty and
    # `iteration` is still 0. Exiting 2 there would leave Step 5 with no
    # sections at all.
    fresh = tmp_path / "state.json"
    fresh.write_text(json.dumps({"iteration": 0, "history": []}))
    proc = run_cli({"iteration": 0, "suggestions": [], "nits": []}, fresh)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"suggestions": [], "nits": [], "carried": 0}


def test_the_real_synthesizers_output_flows_straight_into_the_collector(tmp_path):
    """End to end over the two CLIs the loop actually pipes together.

    Every other fixture here hand-builds findings. That is how the collector
    shipped requiring a per-finding `reviewer` no synthesized finding carries:
    a contract mismatch a hand-built fixture cannot see.
    """
    panel = {
        "findings": [
            {
                "severity": "suggestion",
                "scope": "in_scope",
                "file": "src/a.py",
                "line": 10,
                "summary": "the retry budget is not reset between attempts",
                "source_reviewers": ["correctness"],
            },
            {
                "severity": "nit",
                "scope": "in_scope",
                "file": "src/b.py",
                "line": 4,
                "summary": "the log message says user when it means account",
                "source_reviewers": ["comments"],
            },
        ],
        "suggestion_promotion_threshold": 2,
        "adversary_promotion": True,
        "adversary_solo_promotion": True,
        "demoted": [],
    }
    synthesized = subprocess.run(
        [sys.executable, str(SCRIPT.parent / "promote_findings.py")],
        input=json.dumps(panel),
        capture_output=True,
        text=True,
        check=True,
    )
    partitions = json.loads(synthesized.stdout)
    assert not any("reviewer" in f for f in partitions["suggestions"] + partitions["nits"])

    state = tmp_path / "state.json"
    state.write_text(json.dumps({"iteration": 0, "history": []}))
    payload = {
        "iteration": 1,
        "suggestions": partitions["suggestions"],
        "nits": partitions["nits"],
        "blockers": partitions["blockers"],
        "panel_ran": ["correctness", "comments"],
        "forced_full_sweep": False,
    }
    proc = run_cli(payload, state)
    assert proc.returncode == 0, proc.stderr
    open_sets = json.loads(proc.stdout)
    assert summaries(open_sets["suggestions"]) == ["the retry budget is not reset between attempts"]
    assert summaries(open_sets["nits"]) == ["the log message says user when it means account"]


def test_a_partial_panel_re_raise_does_not_narrow_the_owner_set():
    """The owner set accumulates; it is not read off the newest sighting.

    `source_reviewers` is per-iteration (promote_findings.py counts it within one
    call), so a delta-gated iteration running one of two co-owners re-raises the
    finding with the shorter list. Taking that list would let one persona retire
    what the panel co-owns.
    """
    same = "the tenant id is missing from the cache key"
    both = dict(finding(line=10, summary=same), source_reviewers=["tests", "correctness"])
    narrowed = dict(finding(line=12, summary=same), source_reviewers=["tests"])
    history = [
        entry(1, findings=[both], ran=["tests", "correctness"], mode="full"),
        entry(2, findings=[narrowed], ran=["tests"]),
        entry(3, findings=[], ran=["tests"]),
    ]
    result = collect(current(4, ran=[]), history)
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["first_seen_iteration"] == 1
    # ...and it does resolve once the co-owner reviews again without it.
    resolved = history + [entry(4, findings=[], ran=["tests", "correctness"], mode="full")]
    assert collect(current(5, ran=[]), resolved)["suggestions"] == []


def test_the_fold_de_duplicates_injectively():
    # One persisted candidate answers for at most one restatement: a containment
    # scan would let it absorb two that do not match each other and erase both.
    same = "the tenant id is missing from the cache key"
    history = [entry(2, findings=[finding(line=15, summary=same)], ran=["tests"])]
    payload = current(
        2,
        suggestions=[finding(line=10, summary=same), finding(line=20, summary=same)],
        ran=["tests"],
    )
    assert len(collect(payload, history)["suggestions"]) == 2


def test_pairing_finds_a_maximum_matching_not_a_greedy_one():
    # item_a matches only shared; item_b matches shared and its own. A greedy
    # pass that gives `shared` to item_b strands item_a, whose owners all
    # reviewed again, so it would be dropped despite having been re-raised.
    a = finding("tests", line=10, summary="the tenant id is missing from the cache key")
    b = finding("tests", line=20, summary="the tenant id is missing from the cache key")
    shared = finding("tests", line=15, summary="the tenant id is missing from the cache key")
    own = finding("tests", line=22, summary="the tenant id is missing from the cache key")
    history = [
        entry(1, findings=[a], ran=["tests"]),
        entry(2, findings=[b], ran=["correctness"]),
        entry(3, findings=[shared, own], ran=["tests"]),
    ]
    result = collect(current(4, ran=[]), history)
    assert sorted(i["first_seen_iteration"] for i in result["suggestions"]) == [1, 2]


@pytest.mark.parametrize("lines", [(15, 5), (5, 15)])
def test_fold_finds_all_pairs_regardless_of_current_finding_order(lines):
    same = "the tenant id is missing from the cache key"
    history = [
        entry(2, findings=[finding(line=line, summary=same) for line in (10, 20)], ran=["tests"])
    ]
    payload = current(
        2,
        suggestions=[finding(line=line, summary=same) for line in lines],
        ran=["tests"],
    )
    result = collect(payload, history)
    assert [(item["line"], item["first_seen_iteration"]) for item in result["suggestions"]] == [
        (10, 2),
        (20, 2),
    ]


@pytest.mark.parametrize("evidence_failure", [False, True])
def test_current_deferral_retires_a_skipped_owners_finding(tmp_path, evidence_failure):
    original = finding(summary="parser cache retains stale tokens")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"iteration": 1, "history": [entry(1, findings=[original])]}))
    reviewer = "adversary" if evidence_failure else "correctness"
    raw = {
        **original,
        "detail": "cache invalidation concern",
        "reviewer": reviewer,
        "source_reviewers": [reviewer],
        "scope": "in_scope" if evidence_failure else "out_of_scope",
    }
    if evidence_failure:
        raw["finding_evidence"] = {
            "file": str(tmp_path / "missing.py"),
            "line": 10,
            "snippet": "cache.clear()",
        }
    promotion = subprocess.run(
        [sys.executable, str(SCRIPT.with_name("promote_findings.py"))],
        input=json.dumps(
            {
                "findings": [raw],
                "suggestion_promotion_threshold": 2,
                "adversary_promotion": True,
                "adversary_solo_promotion": True,
                "demoted": [],
            }
        ),
        text=True,
        capture_output=True,
    )
    assert promotion.returncode == 0, promotion.stderr
    partitions = json.loads(promotion.stdout)
    assert len(partitions["deferred"]) == 1
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--state", str(state)],
        input=json.dumps(
            {**partitions, "iteration": 2, "findings": [raw], "panel_ran": ["correctness"]}
        ),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"suggestions": [], "nits": [], "carried": 0}


def test_a_persisted_deferral_and_its_current_copy_settle_only_one_finding():
    original = finding(summary="the tenant id is missing from the cache key")
    deferred = {
        **original,
        "reviewer": "correctness",
        "source_reviewers": ["correctness"],
        "scope": "out_of_scope",
        "line": 15,
    }
    history = [
        entry(1, findings=[{**original, "line": 10}, {**original, "line": 20}], ran=["tests"]),
        entry(2, findings=[deferred], ran=["correctness"]),
    ]
    result = collect(current(2, findings=[deferred], ran=["correctness"]), history)
    assert [(item["line"], item["first_seen_iteration"]) for item in result["suggestions"]] == [
        (20, 1)
    ]


def test_iteration_zero_on_a_resume_still_returns_the_accumulated_sets():
    # §3.6 aborts EXTERNAL_PUSH on a resume with history[] already populated.
    f = finding()
    history = [entry(1, findings=[f], ran=["tests"])]
    result = collect(current(0, ran=[]), history)
    assert summaries(result["suggestions"]) == [f["summary"]]
    # carried is measured against the last round walked, not the number passed.
    assert result["carried"] == 0


def test_an_adversary_that_ran_this_iteration_can_settle_its_own_finding():
    # §4d.0 runs before the MAX_ITERATIONS and approval exits, and the adversary
    # is never in panel_ran.
    f = finding(reviewer="adversary")
    history = [
        entry(1, findings=[f], ran=["tests"], adversary={"verdict": "comment", "findings": []})
    ]
    assert len(collect(current(2, ran=["tests"]), history)["suggestions"]) == 1
    ran_again = current(2, ran=["tests"], adversary={"verdict": "approve", "findings": []})
    assert collect(ran_again, history)["suggestions"] == []
    shallow = current(
        2,
        ran=["tests"],
        adversary={"verdict": "approve", "findings": [], "shallow_blocker": True},
    )
    assert len(collect(shallow, history)["suggestions"]) == 1
