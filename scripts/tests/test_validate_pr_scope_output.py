"""Tests for scripts/validate_pr_scope_output.py."""

from __future__ import annotations

import io
import json

import pytest
from validate_pr_scope_output import (  # type: ignore[import-not-found]
    PrScopeOutputValidationError,
    _main,
    validate_pr_scope_output,
)

PER_FILE = [
    {
        "path": "apps/web/server/middleware/catalog-preview.ts",
        "added": 410,
        "deleted": 0,
    },
    {
        "path": "apps/web/server/middleware/catalog-preview.test.ts",
        "added": 220,
        "deleted": 0,
    },
    {
        "path": "apps/web/server/billing/invoice-renderer.ts",
        "added": 380,
        "deleted": 0,
    },
    {
        "path": "apps/web/server/billing/invoice-renderer.test.ts",
        "added": 140,
        "deleted": 0,
    },
    {
        "path": "apps/web/server/billing/legacy-pdf.ts",
        "added": 0,
        "deleted": 60,
    },
    {
        "path": "apps/web/utils/strings.ts",
        "added": 50,
        "deleted": 0,
    },
    {
        "path": "apps/web/utils/strings.test.ts",
        "added": 40,
        "deleted": 0,
    },
    {
        "path": "docs/changelog.md",
        "added": 8,
        "deleted": 0,
    },
]
EXCLUDED_PATHS = ["pnpm-lock.yaml"]
NEW_LOC_TOTAL = 1248
CATALOG_SPLIT = {
    "name": "catalog-preview middleware",
    "rationale": "Isolated feature.",
    "files": [
        "apps/web/server/middleware/catalog-preview.ts",
        "apps/web/server/middleware/catalog-preview.test.ts",
    ],
    "estimated_new_loc": 630,
}
INVOICE_SPLIT = {
    "name": "invoice-renderer refactor",
    "rationale": "Independent billing refactor.",
    "files": [
        "apps/web/server/billing/invoice-renderer.ts",
        "apps/web/server/billing/invoice-renderer.test.ts",
        "apps/web/server/billing/legacy-pdf.ts",
    ],
    "estimated_new_loc": 520,
}
REMAINING_PATHS = [
    "apps/web/utils/strings.ts",
    "apps/web/utils/strings.test.ts",
    "docs/changelog.md",
]


def make_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "gate": "pr-scope",
        "verdict": "request_split",
        "summary": "Split catalog and billing work.",
        "splits": [CATALOG_SPLIT, INVOICE_SPLIT],
        "remaining_in_original": REMAINING_PATHS,
    }
    payload.update(updates)
    return payload


def test_validate_pr_scope_output_accepts_complete_partition() -> None:
    validate_pr_scope_output(
        payload=make_payload(),
        per_file=PER_FILE,
        excluded_paths=EXCLUDED_PATHS,
        new_loc_total=NEW_LOC_TOTAL,
    )


def test_validate_pr_scope_output_accepts_atomic_verdict() -> None:
    validate_pr_scope_output(
        payload={"gate": "pr-scope", "verdict": "atomic", "summary": "PR is already atomic."},
        per_file=PER_FILE,
        excluded_paths=EXCLUDED_PATHS,
        new_loc_total=NEW_LOC_TOTAL,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "gate": "pr-scope",
            "verdict": "atomic",
            "summary": "PR is already atomic.",
            "splits": [],
        },
        {
            "gate": "pr-scope",
            "verdict": "atomic",
            "summary": "PR is already atomic.",
            "remaining_in_original": [],
        },
        {
            "gate": "pr-scope",
            "verdict": "atomic",
            "summary": "PR is already atomic.",
            "extra": True,
        },
    ],
)
def test_validate_pr_scope_output_rejects_atomic_shape_extras(
    payload: dict[str, object],
) -> None:
    with pytest.raises(PrScopeOutputValidationError, match="atomic payload"):
        validate_pr_scope_output(
            payload=payload,
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_request_split_top_level_extras() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="request_split payload"):
        validate_pr_scope_output(
            payload=make_payload(extra=True),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_split_extras() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="split has unexpected"):
        validate_pr_scope_output(
            payload=make_payload(splits=[{**CATALOG_SPLIT, "extra": True}, INVOICE_SPLIT]),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_partial_file_extras() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="partial file entry"):
        validate_pr_scope_output(
            payload=make_payload(
                splits=[
                    CATALOG_SPLIT,
                    INVOICE_SPLIT,
                    {
                        "name": "strings-partial",
                        "rationale": "Partial take of strings.",
                        "files": [
                            {
                                "path": "apps/web/utils/strings.ts",
                                "hunks": ["L1-L10"],
                                "extra": True,
                            }
                        ],
                        "estimated_new_loc": 10,
                    },
                ],
                remaining_in_original=REMAINING_PATHS,
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


@pytest.mark.parametrize("gate", [None, "other-gate"])
def test_validate_pr_scope_output_rejects_wrong_gate(gate: object) -> None:
    payload = make_payload()
    if gate is None:
        payload.pop("gate")
    else:
        payload["gate"] = gate

    with pytest.raises(PrScopeOutputValidationError, match="payload.gate"):
        validate_pr_scope_output(
            payload=payload,
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


@pytest.mark.parametrize("verdict", [None, "bogus"])
def test_validate_pr_scope_output_rejects_invalid_verdict(verdict: object) -> None:
    payload = make_payload()
    if verdict is None:
        payload.pop("verdict")
    else:
        payload["verdict"] = verdict

    with pytest.raises(PrScopeOutputValidationError, match="payload.verdict"):
        validate_pr_scope_output(
            payload=payload,
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"gate": "pr-scope", "verdict": "atomic"},
        {"gate": "pr-scope", "verdict": "atomic", "summary": " "},
        {
            "gate": "pr-scope",
            "verdict": "request_split",
            "splits": [CATALOG_SPLIT, INVOICE_SPLIT],
            "remaining_in_original": REMAINING_PATHS,
        },
        make_payload(summary=""),
    ],
)
def test_validate_pr_scope_output_rejects_missing_or_blank_summary(
    payload: dict[str, object],
) -> None:
    with pytest.raises(PrScopeOutputValidationError, match="payload.summary"):
        validate_pr_scope_output(
            payload=payload,
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_more_than_four_splits() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="more than 4 splits"):
        validate_pr_scope_output(
            payload=make_payload(
                summary="Too many splits.",
                splits=[
                    {
                        "name": "preview",
                        "rationale": "Preview middleware.",
                        "files": ["apps/web/server/middleware/catalog-preview.ts"],
                        "estimated_new_loc": 410,
                    },
                    {
                        "name": "preview-tests",
                        "rationale": "Preview tests.",
                        "files": ["apps/web/server/middleware/catalog-preview.test.ts"],
                        "estimated_new_loc": 220,
                    },
                    {
                        "name": "invoice",
                        "rationale": "Invoice renderer.",
                        "files": ["apps/web/server/billing/invoice-renderer.ts"],
                        "estimated_new_loc": 380,
                    },
                    {
                        "name": "invoice-tests",
                        "rationale": "Invoice tests.",
                        "files": [
                            "apps/web/server/billing/invoice-renderer.test.ts",
                            "apps/web/server/billing/legacy-pdf.ts",
                        ],
                        "estimated_new_loc": 140,
                    },
                    {
                        "name": "strings",
                        "rationale": "String utilities and docs.",
                        "files": [
                            "apps/web/utils/strings.ts",
                            "apps/web/utils/strings.test.ts",
                            "docs/changelog.md",
                        ],
                        "estimated_new_loc": 98,
                    },
                ],
                remaining_in_original=[],
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_duplicate_split_names() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="split.name 'duplicate'"):
        validate_pr_scope_output(
            payload=make_payload(
                splits=[
                    {**CATALOG_SPLIT, "name": "duplicate"},
                    {**INVOICE_SPLIT, "name": "duplicate"},
                ],
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_unknown_split_dependency() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="unknown split 'missing'"):
        validate_pr_scope_output(
            payload=make_payload(splits=[{**CATALOG_SPLIT, "depends_on": ["missing"]}]),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_null_dependency_before_persistence() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="depends_on must be a list"):
        validate_pr_scope_output(
            payload=make_payload(splits=[{**CATALOG_SPLIT, "depends_on": None}, INVOICE_SPLIT]),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_self_dependency() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="cannot reference itself"):
        validate_pr_scope_output(
            payload=make_payload(
                splits=[
                    {
                        **CATALOG_SPLIT,
                        "depends_on": [CATALOG_SPLIT["name"]],
                    },
                    INVOICE_SPLIT,
                ],
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_partial_split_missing_from_remaining() -> None:
    with pytest.raises(
        PrScopeOutputValidationError,
        match="partial-file split paths must also remain",
    ):
        validate_pr_scope_output(
            payload=make_payload(
                summary="Partial split without remainder.",
                splits=[
                    CATALOG_SPLIT,
                    INVOICE_SPLIT,
                    {
                        "name": "strings-partial",
                        "rationale": "Partial take of strings.",
                        "files": [{"path": "apps/web/utils/strings.ts", "hunks": ["L1-L10"]}],
                        "estimated_new_loc": 10,
                    },
                ],
                remaining_in_original=[
                    "apps/web/utils/strings.test.ts",
                    "docs/changelog.md",
                ],
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_accepts_reasonable_partial_split() -> None:
    validate_pr_scope_output(
        payload=make_payload(
            summary="Whole-file splits plus a partial move out of strings.",
            splits=[
                CATALOG_SPLIT,
                INVOICE_SPLIT,
                {
                    "name": "strings-partial",
                    "rationale": "Move a single hunk out of the strings utilities.",
                    "files": [{"path": "apps/web/utils/strings.ts", "hunks": ["L1-L20"]}],
                    "estimated_new_loc": 20,
                },
            ],
            remaining_in_original=REMAINING_PATHS,
        ),
        per_file=PER_FILE,
        excluded_paths=EXCLUDED_PATHS,
        new_loc_total=NEW_LOC_TOTAL,
    )


def test_validate_pr_scope_output_rejects_whole_file_overcount_in_partial_split() -> None:
    with pytest.raises(
        PrScopeOutputValidationError,
        match="implies whole-file splits exceed",
    ):
        validate_pr_scope_output(
            payload=make_payload(
                splits=[
                    {
                        "name": "mixed split",
                        "rationale": "Whole-file LOC understated against the partial estimate.",
                        "files": [
                            "src/small.py",
                            {"path": "src/large.py", "hunks": ["L1-L10"]},
                        ],
                        "estimated_new_loc": 50,
                    }
                ],
                remaining_in_original=["src/large.py"],
            ),
            per_file=[
                {"path": "src/large.py", "added": 1000, "deleted": 0},
                {"path": "src/small.py", "added": 248, "deleted": 0},
            ],
            excluded_paths=[],
            new_loc_total=1248,
        )


def test_validate_pr_scope_output_rejects_whole_and_partial_same_path() -> None:
    with pytest.raises(
        PrScopeOutputValidationError,
        match="cannot be both whole-file and partial-file assigned",
    ):
        validate_pr_scope_output(
            payload=make_payload(
                summary="Same path as whole and partial.",
                splits=[
                    CATALOG_SPLIT,
                    {
                        "name": "strings-mixed",
                        "rationale": "Conflicting assignment.",
                        "files": [
                            "apps/web/utils/strings.ts",
                            {"path": "apps/web/utils/strings.ts", "hunks": ["L1-L5"]},
                        ],
                        "estimated_new_loc": 50,
                    },
                ],
                remaining_in_original=REMAINING_PATHS,
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_duplicate_per_file_paths() -> None:
    duplicate_per_file = [
        *PER_FILE,
        {
            "path": "docs/changelog.md",
            "added": 4,
            "deleted": 0,
        },
    ]

    with pytest.raises(PrScopeOutputValidationError, match="per_file\\[8\\].path"):
        validate_pr_scope_output(
            payload=make_payload(),
            per_file=duplicate_per_file,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL + 4,
        )


def test_validate_pr_scope_output_rejects_new_loc_total_mismatch() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="new_loc_total must equal"):
        validate_pr_scope_output(
            payload=make_payload(),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL + 1,
        )


def test_validate_pr_scope_output_rejects_excluded_path_in_split() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="excluded path"):
        validate_pr_scope_output(
            payload=make_payload(
                summary="Bad split.",
                splits=[
                    {
                        "name": "deps",
                        "rationale": "Wrongly includes lockfile.",
                        "files": ["pnpm-lock.yaml"],
                        "estimated_new_loc": NEW_LOC_TOTAL,
                    }
                ],
                remaining_in_original=[entry["path"] for entry in PER_FILE],
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_duplicate_whole_file_assignment() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="assigned more than once"):
        validate_pr_scope_output(
            payload=make_payload(
                summary="Duplicates a file.",
                splits=[
                    {
                        "name": "split-a",
                        "rationale": "A.",
                        "files": ["apps/web/server/middleware/catalog-preview.ts"],
                        "estimated_new_loc": 410,
                    },
                    {
                        "name": "split-b",
                        "rationale": "B.",
                        "files": ["apps/web/server/middleware/catalog-preview.ts"],
                        "estimated_new_loc": 838,
                    },
                ],
                remaining_in_original=[
                    entry["path"]
                    for entry in PER_FILE
                    if entry["path"] != "apps/web/server/middleware/catalog-preview.ts"
                ],
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_whole_file_split_remaining_overlap() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="cannot appear in both"):
        validate_pr_scope_output(
            payload=make_payload(
                summary="Keeps split file in original PR.",
                remaining_in_original=[
                    "apps/web/server/middleware/catalog-preview.ts",
                    *REMAINING_PATHS,
                ],
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_duplicate_partial_assignment() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="assigned more than once"):
        validate_pr_scope_output(
            payload=make_payload(
                summary="Duplicates a partial path.",
                splits=[
                    {
                        "name": "split-a",
                        "rationale": "A.",
                        "files": [{"path": "apps/web/utils/strings.ts", "hunks": ["L1-L10"]}],
                        "estimated_new_loc": 10,
                    },
                    {
                        "name": "split-b",
                        "rationale": "B.",
                        "files": [{"path": "apps/web/utils/strings.ts", "hunks": ["L20-L30"]}],
                        "estimated_new_loc": 20,
                    },
                ],
                remaining_in_original=[
                    entry["path"]
                    for entry in PER_FILE
                    if entry["path"] != "apps/web/utils/strings.ts"
                ]
                + ["apps/web/utils/strings.ts"],
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_duplicate_remaining_entry() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="listed more than once"):
        validate_pr_scope_output(
            payload=make_payload(
                summary="Duplicates remaining path.",
                remaining_in_original=[
                    "apps/web/utils/strings.ts",
                    "apps/web/utils/strings.test.ts",
                    "docs/changelog.md",
                    "docs/changelog.md",
                ],
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_missing_file_coverage() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="missing changed files"):
        validate_pr_scope_output(
            payload=make_payload(
                summary="Misses changelog.",
                remaining_in_original=[
                    "apps/web/utils/strings.ts",
                    "apps/web/utils/strings.test.ts",
                ],
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_loc_mismatch_without_partial_splits() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="estimated_new_loc total"):
        validate_pr_scope_output(
            payload=make_payload(
                summary="Bad math.",
                splits=[
                    {**CATALOG_SPLIT, "estimated_new_loc": 600},
                    {**INVOICE_SPLIT, "estimated_new_loc": 500},
                ],
            ),
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_gross_loc_mismatch_with_partial_split() -> None:
    with pytest.raises(
        PrScopeOutputValidationError,
        match="exceeds the partials' total LOC",
    ):
        validate_pr_scope_output(
            payload={
                "gate": "pr-scope",
                "verdict": "request_split",
                "summary": "Impossible partial math.",
                "splits": [
                    {
                        "name": "partial-utils",
                        "rationale": "Moves one hunk only.",
                        "files": [
                            {"path": "apps/web/utils/strings.ts", "hunks": ["L1-L10"]},
                        ],
                        "estimated_new_loc": 9999,
                    }
                ],
                "remaining_in_original": [entry["path"] for entry in PER_FILE],
            },
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_zero_loc_partial_split() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="positive estimated_new_loc"):
        validate_pr_scope_output(
            payload={
                "gate": "pr-scope",
                "verdict": "request_split",
                "summary": "Impossible partial math.",
                "splits": [
                    {
                        "name": "partial-utils",
                        "rationale": "Moves one hunk only.",
                        "files": [
                            {"path": "apps/web/utils/strings.ts", "hunks": ["L1-L10"]},
                        ],
                        "estimated_new_loc": 0,
                    }
                ],
                "remaining_in_original": [entry["path"] for entry in PER_FILE],
            },
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_malformed_split_shape() -> None:
    with pytest.raises(PrScopeOutputValidationError, match="split.name must be a non-empty string"):
        validate_pr_scope_output(
            payload={
                "gate": "pr-scope",
                "verdict": "request_split",
                "summary": "Missing split metadata.",
                "splits": [
                    {
                        "files": ["apps/web/server/middleware/catalog-preview.ts"],
                        "estimated_new_loc": 410,
                    }
                ],
                "remaining_in_original": [
                    entry["path"]
                    for entry in PER_FILE
                    if entry["path"] != "apps/web/server/middleware/catalog-preview.ts"
                ],
            },
            per_file=PER_FILE,
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_validate_pr_scope_output_rejects_per_file_entry_missing_path_cleanly() -> None:
    malformed_per_file = [{"added": 10, "deleted": 0}]

    with pytest.raises(PrScopeOutputValidationError, match="per_file\\[0\\].path"):
        validate_pr_scope_output(
            payload=make_payload(),
            per_file=malformed_per_file,  # type: ignore[arg-type]
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


@pytest.mark.parametrize("added", [-1, "10", True])
def test_validate_pr_scope_output_rejects_malformed_per_file_added_cleanly(
    added: object,
) -> None:
    malformed_per_file = [{"path": "apps/web/utils/strings.ts", "added": added}]

    with pytest.raises(PrScopeOutputValidationError, match="per_file\\[0\\].added"):
        validate_pr_scope_output(
            payload=make_payload(),
            per_file=malformed_per_file,  # type: ignore[arg-type]
            excluded_paths=EXCLUDED_PATHS,
            new_loc_total=NEW_LOC_TOTAL,
        )


@pytest.mark.parametrize("excluded_path", ["", 123])
def test_validate_pr_scope_output_rejects_malformed_excluded_paths_cleanly(
    excluded_path: object,
) -> None:
    with pytest.raises(PrScopeOutputValidationError, match="excluded_paths\\[0\\]"):
        validate_pr_scope_output(
            payload=make_payload(),
            per_file=PER_FILE,
            excluded_paths=[excluded_path],  # type: ignore[list-item]
            new_loc_total=NEW_LOC_TOTAL,
        )


def test_main_accepts_valid_payload_from_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(make_payload())))

    rc = _main(
        [
            "--per-file-json",
            json.dumps(PER_FILE),
            "--excluded-paths-json",
            json.dumps(EXCLUDED_PATHS),
            "--new-loc-total",
            str(NEW_LOC_TOTAL),
        ]
    )

    assert rc == 0


def test_main_returns_2_on_invalid_json_argument(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(make_payload())))

    rc = _main(
        [
            "--per-file-json",
            "{broken",
            "--excluded-paths-json",
            json.dumps(EXCLUDED_PATHS),
            "--new-loc-total",
            str(NEW_LOC_TOTAL),
        ]
    )

    assert rc == 2
    assert "validate_pr_scope_output: failed to parse per-file JSON" in capsys.readouterr().err


def test_main_accepts_per_file_and_excluded_paths_from_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(make_payload())))
    per_file_path = tmp_path / "per-file.json"
    per_file_path.write_text(json.dumps(PER_FILE), encoding="utf-8")
    excluded_paths_path = tmp_path / "excluded.json"
    excluded_paths_path.write_text(json.dumps(EXCLUDED_PATHS), encoding="utf-8")

    rc = _main(
        [
            "--per-file-json-file",
            str(per_file_path),
            "--excluded-paths-json-file",
            str(excluded_paths_path),
            "--new-loc-total",
            str(NEW_LOC_TOTAL),
        ]
    )

    assert rc == 0


def test_main_rejects_both_inline_and_file_for_per_file(
    capsys, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(make_payload())))
    per_file_path = tmp_path / "per-file.json"
    per_file_path.write_text(json.dumps(PER_FILE), encoding="utf-8")

    rc = _main(
        [
            "--per-file-json",
            json.dumps(PER_FILE),
            "--per-file-json-file",
            str(per_file_path),
            "--excluded-paths-json",
            json.dumps(EXCLUDED_PATHS),
            "--new-loc-total",
            str(NEW_LOC_TOTAL),
        ]
    )

    assert rc == 2
    assert (
        "validate_pr_scope_output: --per-file-json and --per-file-json-file are mutually exclusive"
        in capsys.readouterr().err
    )


def test_main_rejects_missing_per_file_input(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(make_payload())))

    rc = _main(
        [
            "--excluded-paths-json",
            json.dumps(EXCLUDED_PATHS),
            "--new-loc-total",
            str(NEW_LOC_TOTAL),
        ]
    )

    assert rc == 2
    assert (
        "validate_pr_scope_output: one of --per-file-json or --per-file-json-file is required"
        in capsys.readouterr().err
    )


def test_main_rejects_missing_excluded_paths_input(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(make_payload())))

    rc = _main(
        [
            "--per-file-json",
            json.dumps(PER_FILE),
            "--new-loc-total",
            str(NEW_LOC_TOTAL),
        ]
    )

    assert rc == 2
    assert (
        "validate_pr_scope_output: "
        "one of --excluded-paths-json or --excluded-paths-json-file is required"
        in capsys.readouterr().err
    )


def test_main_returns_2_on_missing_per_file_json_file(
    capsys, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(make_payload())))

    rc = _main(
        [
            "--per-file-json-file",
            str(tmp_path / "missing.json"),
            "--excluded-paths-json",
            json.dumps(EXCLUDED_PATHS),
            "--new-loc-total",
            str(NEW_LOC_TOTAL),
        ]
    )

    assert rc == 2
    assert "validate_pr_scope_output: failed to read per-file JSON file" in capsys.readouterr().err
