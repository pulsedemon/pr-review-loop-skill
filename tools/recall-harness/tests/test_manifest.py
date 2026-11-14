"""The committed corpus-manifest.csv must be a superset of every labeled PR and
of every collected corpus file (so neither a label nor a corpus record can
reference a PR outside the documented corpus), and the collector's --manifest /
single-repo arg modes are mutually exclusive."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import check_manifest_drift  # type: ignore[import-not-found]
import collect_pr_corpus  # type: ignore[import-not-found]
import pytest

HARNESS = Path(__file__).resolve().parents[1]
COLLECT_SCRIPT = HARNESS / "collect_pr_corpus.py"


def _triples(path: Path) -> set[tuple[str, str, str]]:
    with path.open(newline="") as f:
        return {(r["owner"], r["repo"], str(r["pr"])) for r in csv.DictReader(f)}


def test_labels_are_subset_of_manifest():
    labels = _triples(HARNESS / "labels.csv")
    manifest = _triples(HARNESS / "corpus-manifest.csv")
    missing = labels - manifest
    assert not missing, f"labeled PRs absent from corpus-manifest.csv: {sorted(missing)}"


def test_empty_manifest_produces_usable_empty_corpus(tmp_path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("owner,repo,pr\n")
    labels = tmp_path / "labels.csv"
    labels.write_text("owner,repo,pr,bucket,finding_id,label,notes\n")
    corpus = tmp_path / "corpus"
    outputs = [
        "--corpus-dir",
        str(corpus),
        "--unmatched-dir",
        str(tmp_path / "unmatched"),
        "--matched-dir",
        str(tmp_path / "matched"),
        "--loop-unmatched-dir",
        str(tmp_path / "loop-unmatched"),
    ]
    commands = [
        [str(COLLECT_SCRIPT), "--manifest", str(manifest), "--out-dir", str(corpus)],
        [str(HARNESS / "match_external.py"), *outputs],
        [str(HARNESS / "report.py"), *outputs, "--labels", str(labels)],
    ]
    for command in commands:
        result = subprocess.run([sys.executable, *command], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    assert corpus.is_dir()
    assert list(corpus.iterdir()) == []
    assert "PRs analyzed: 0" in result.stdout


def test_corpus_is_subset_of_manifest():
    """A corpus file for an unmanifested PR means `--manifest` no longer rebuilds
    the corpus the labels were derived from. That drift is how an ad-hoc
    collection from a second repo outlived its own reproducibility."""
    corpus_dir = HARNESS / "corpus"
    if not corpus_dir.is_dir():
        pytest.skip("corpus/ is gitignored and absent on a fresh checkout")
    collected = {
        (owner_dir.name, repo_dir.name, pr_file.stem.removeprefix("pr-"))
        for owner_dir in corpus_dir.iterdir()
        if owner_dir.is_dir()
        for repo_dir in owner_dir.iterdir()
        if repo_dir.is_dir()
        for pr_file in repo_dir.glob("pr-*.json")
    }
    missing = collected - _triples(HARNESS / "corpus-manifest.csv")
    assert not missing, f"collected PRs absent from corpus-manifest.csv: {sorted(missing)}"


def test_manifest_and_single_repo_modes_are_mutually_exclusive():
    result = subprocess.run(
        [
            sys.executable,
            str(COLLECT_SCRIPT),
            "--manifest",
            str(HARNESS / "corpus-manifest.csv"),
            "--owner",
            "o",
            "--repo",
            "r",
            "--pr-list",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    # Assert the guard's specific message, not just "--manifest": the mutual-
    # exclusion parser.error fires before any gh call, so this stays hermetic
    # and would FAIL (not silently pass via the hard-fail/access path) if the
    # guard were removed.
    assert "mutually exclusive" in result.stderr


def test_missing_mode_errors():
    result = subprocess.run(
        [sys.executable, str(COLLECT_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "provide --manifest" in result.stderr


def test_read_manifest_parses_triples(tmp_path):
    manifest = tmp_path / "m.csv"
    manifest.write_text("owner,repo,pr\nacme,api,12\nacme,web,3\n")
    assert collect_pr_corpus.read_manifest(manifest) == [
        ("acme", "api", 12),
        ("acme", "web", 3),
    ]


def test_read_manifest_raises_on_non_numeric_pr(tmp_path):
    manifest = tmp_path / "m.csv"
    manifest.write_text("owner,repo,pr\nacme,api,notanumber\n")
    # The pr column is int-coerced so a non-numeric value fails loudly rather
    # than producing a corpus filename built from a bad PR id.
    with pytest.raises(ValueError):
        collect_pr_corpus.read_manifest(manifest)


def test_include_open_not_valid_with_manifest():
    result = subprocess.run(
        [
            sys.executable,
            str(COLLECT_SCRIPT),
            "--manifest",
            str(HARNESS / "corpus-manifest.csv"),
            "--include-open",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    # parser.error fires before any gh call, so this stays hermetic and would
    # FAIL (not silently pass) if the guard were dropped.
    assert "not valid with --manifest" in result.stderr


def test_owner_repo_required_without_manifest():
    result = subprocess.run(
        [sys.executable, str(COLLECT_SCRIPT), "--pr-list", "1"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--owner and --repo are required without --manifest" in result.stderr


def test_single_repo_mode_requires_pr_list_or_merged_since():
    # owner+repo with neither --pr-list nor --merged-since must error cleanly
    # rather than fall through to the malformed `gh pr list --search merged:>=None`.
    result = subprocess.run(
        [sys.executable, str(COLLECT_SCRIPT), "--owner", "o", "--repo", "r"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--pr-list or --merged-since" in result.stderr


def test_manifest_mode_collects_grouped_corpus(tmp_path, monkeypatch):
    # Happy path: --manifest groups by (owner, repo) and writes one nested
    # <owner>/<repo>/pr-<N>.json per listed PR, returning 0.
    manifest = tmp_path / "m.csv"
    manifest.write_text("owner,repo,pr\nacme,api,12\nacme,api,7\nacme,web,3\n")
    out_dir = tmp_path / "corpus"
    stale = out_dir / "acme" / "old" / "pr-99.json"
    stale.parent.mkdir(parents=True)
    stale.write_text('{"pr":99}\n')
    retained = stale.with_name("notes.txt")
    retained.write_text("retain this file\n")

    def fake_collect_pr(owner, repo, pr_number, include_open=False):
        return {"owner": owner, "repo": repo, "pr_number": pr_number}

    monkeypatch.setattr(collect_pr_corpus, "collect_pr", fake_collect_pr)
    argv = ["collect_pr_corpus.py", "--manifest", str(manifest), "--out-dir", str(out_dir)]
    monkeypatch.setattr(sys, "argv", argv)

    assert collect_pr_corpus.main() == 0
    assert (out_dir / "acme" / "api" / "pr-12.json").is_file()
    assert (out_dir / "acme" / "api" / "pr-7.json").is_file()
    assert (out_dir / "acme" / "web" / "pr-3.json").is_file()
    assert not stale.exists()
    assert retained.read_text() == "retain this file\n"
    assert sorted(str(path.relative_to(out_dir)) for path in out_dir.glob("*/*/pr-*.json")) == [
        "acme/api/pr-12.json",
        "acme/api/pr-7.json",
        "acme/web/pr-3.json",
    ]


def test_manifest_mode_hard_fails_on_unreachable_repo(tmp_path, monkeypatch, capsys):
    # PR contract: --manifest hard-fails (return 1, no silent skip) when a
    # listed repo cannot be reached, rather than producing a partial corpus.
    manifest = tmp_path / "m.csv"
    manifest.write_text("owner,repo,pr\nacme,api,12\n")
    out_dir = tmp_path / "corpus"
    stale = out_dir / "acme" / "old" / "pr-99.json"
    stale.parent.mkdir(parents=True)
    stale.write_text('{"pr":99}\n')

    def boom(owner, repo, pr_number, include_open=False):
        raise subprocess.CalledProcessError(1, ["gh"], stderr="no access")

    monkeypatch.setattr(collect_pr_corpus, "collect_pr", boom)
    argv = ["collect_pr_corpus.py", "--manifest", str(manifest), "--out-dir", str(out_dir)]
    monkeypatch.setattr(sys, "argv", argv)

    assert collect_pr_corpus.main() == 1
    assert "cannot collect acme/api" in capsys.readouterr().err
    assert stale.read_text() == '{"pr":99}\n'


# The drift check exists because nothing else compares the manifest against the
# merged set. `test_corpus_is_subset_of_manifest` above compares two local
# artifacts and skips when corpus/ is absent, which is always true on CI's
# fresh checkout, so a PR merged into neither corpus nor manifest is invisible
# to it.
#
# Mutation-tested before requesting review:
#   - drop a merged PR row from the manifest -> exit 1 and that PR named in
#     stderr (verified against the live repo: it caught #105, unmanifested at
#     the time).
#   - add a manifest row the merged set lacks -> still exit 0. a PR merged
#     before the --merged-since window is legitimately manifested.
#   - point owner/repo at a repo the manifest also lists -> rows for other
#     repos are filtered out rather than counted as coverage.
#   - drop the FileNotFoundError/JSONDecodeError handler -> both fetch-failure
#     tests fail. only CalledProcessError was caught at first, so a missing gh
#     escaped as a stack trace: still non-zero, but it reads in the workflow
#     log like drift rather than a broken fetch.
def _drift(monkeypatch, manifest, merged, owner="acme", repo="api"):
    monkeypatch.setattr(check_manifest_drift, "list_merged_prs", lambda *_: merged)
    argv = [
        "check_manifest_drift.py",
        "--owner",
        owner,
        "--repo",
        repo,
        "--merged-since",
        "2026-01-01",
        "--manifest",
        str(manifest),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    return check_manifest_drift.main()


def test_drift_check_fails_and_names_missing_prs(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "m.csv"
    manifest.write_text("owner,repo,pr\nacme,api,1\n")

    assert _drift(monkeypatch, manifest, [1, 2, 3]) == 1
    err = capsys.readouterr().err
    # The numbers must appear: a bare "manifest is stale" leaves the operator
    # diffing 70+ rows by hand.
    assert "2,3" in err


def test_drift_check_passes_when_manifest_covers_merged_set(tmp_path, monkeypatch):
    manifest = tmp_path / "m.csv"
    manifest.write_text("owner,repo,pr\nacme,api,1\nacme,api,2\n")

    assert _drift(monkeypatch, manifest, [1, 2]) == 0


def test_drift_check_allows_manifest_superset(tmp_path, monkeypatch):
    # A PR merged before the --merged-since window is in the manifest but not
    # the query result. That is not drift, and failing on it would make the
    # check unpassable for any corpus with history.
    manifest = tmp_path / "m.csv"
    manifest.write_text("owner,repo,pr\nacme,api,1\nacme,api,2\nacme,api,3\n")

    assert _drift(monkeypatch, manifest, [2, 3]) == 0


def test_drift_check_ignores_other_repos(tmp_path, monkeypatch, capsys):
    # The manifest is multi-repo by design. Rows for a different repo must not
    # count as coverage for the one being checked.
    manifest = tmp_path / "m.csv"
    manifest.write_text("owner,repo,pr\nacme,web,7\n")

    assert _drift(monkeypatch, manifest, [7]) == 1
    assert "7" in capsys.readouterr().err


def test_drift_check_errors_on_missing_manifest(tmp_path, monkeypatch, capsys):
    assert _drift(monkeypatch, tmp_path / "absent.csv", [1]) == 2
    assert "no manifest" in capsys.readouterr().err


def test_drift_check_exits_2_when_gh_is_missing(tmp_path, monkeypatch, capsys):
    # The script promises exit 2 on a fetch error. A missing gh raises
    # FileNotFoundError, not CalledProcessError, so without an explicit handler
    # it escapes as a stack trace -- which exits non-zero and reads in the
    # workflow log like drift the operator has to go chase.
    manifest = tmp_path / "m.csv"
    manifest.write_text("owner,repo,pr\nacme,api,1\n")

    def boom(*_):
        raise FileNotFoundError(2, "No such file or directory: 'gh'")

    monkeypatch.setattr(check_manifest_drift, "list_merged_prs", boom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_manifest_drift.py",
            "--owner",
            "acme",
            "--repo",
            "api",
            "--merged-since",
            "2026-01-01",
            "--manifest",
            str(manifest),
        ],
    )

    assert check_manifest_drift.main() == 2
    assert "FileNotFoundError" in capsys.readouterr().err


def test_drift_check_exits_2_on_non_json_gh_output(tmp_path, monkeypatch, capsys):
    # Same contract for a gh that returns something other than the requested
    # JSON: the merged set is unknown, not empty. Reporting "covers all 0
    # merged PRs" would be a false all-clear.
    manifest = tmp_path / "m.csv"
    manifest.write_text("owner,repo,pr\nacme,api,1\n")

    def boom(*_):
        raise json.JSONDecodeError("Expecting value", "not json", 0)

    monkeypatch.setattr(check_manifest_drift, "list_merged_prs", boom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_manifest_drift.py",
            "--owner",
            "acme",
            "--repo",
            "api",
            "--merged-since",
            "2026-01-01",
            "--manifest",
            str(manifest),
        ],
    )

    assert check_manifest_drift.main() == 2
    assert "JSONDecodeError" in capsys.readouterr().err


def test_list_merged_prs_pins_query_and_sorts(monkeypatch):
    # Every drift test monkeypatches list_merged_prs, so nothing executed the
    # function itself: a regression in the gh arguments, the JSON parse, or the
    # ordering would break the collector and the drift check while the suite
    # stayed green. Pins the merged-state/date query and the sorted result.
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps([{"number": 9}, {"number": 3}, {"number": 11}])
        )

    monkeypatch.setattr(collect_pr_corpus.subprocess, "run", fake_run)

    assert collect_pr_corpus.list_merged_prs("acme", "api", "2026-01-01") == [3, 9, 11]

    cmd = captured["cmd"]
    assert cmd[:3] == ["gh", "pr", "list"]
    assert "--repo" in cmd and cmd[cmd.index("--repo") + 1] == "acme/api"
    # --state merged and the merged:>= search are what scope the corpus; a drift
    # check that silently included open PRs would report phantom drift forever.
    assert cmd[cmd.index("--state") + 1] == "merged"
    assert cmd[cmd.index("--search") + 1] == "merged:>=2026-01-01"


def test_drift_check_exits_2_on_unparseable_manifest(tmp_path, monkeypatch, capsys):
    # A manifest that will not parse leaves coverage unknown, same as a failed
    # fetch. Without this handler read_manifest's ValueError escapes as a
    # traceback: still non-zero, but it reads as drift rather than a bad file.
    manifest = tmp_path / "m.csv"
    manifest.write_text("owner,repo,pr\nacme,api,notanumber\n")

    monkeypatch.setattr(check_manifest_drift, "list_merged_prs", lambda *_: [1])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_manifest_drift.py",
            "--owner",
            "acme",
            "--repo",
            "api",
            "--merged-since",
            "2026-01-01",
            "--manifest",
            str(manifest),
        ],
    )

    assert check_manifest_drift.main() == 2
    assert "cannot read" in capsys.readouterr().err
