#!/usr/bin/env python3
"""Validate deterministic invariants for Step 3.5 PR-scope gate output."""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any

from _json_args import load_json_or_file

MAX_SPLITS = 4
ATOMIC_PAYLOAD_KEYS = {"gate", "verdict", "summary"}
REQUEST_SPLIT_PAYLOAD_KEYS = {"gate", "verdict", "summary", "splits", "remaining_in_original"}
SPLIT_KEYS = {"name", "rationale", "files", "estimated_new_loc", "depends_on"}
PARTIAL_FILE_KEYS = {"path", "hunks"}


class PrScopeOutputValidationError(ValueError):
    """Raised when PR-scope output violates deterministic partition rules."""


def _require_non_negative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PrScopeOutputValidationError(f"{label} must be a non-negative integer")
    return value


def _require_non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PrScopeOutputValidationError(f"{label} must be a non-empty string")
    return value


def _reject_unexpected_keys(obj: dict[str, Any], *, allowed: set[str], label: str) -> None:
    unexpected = sorted(set(obj) - allowed)
    if unexpected:
        raise PrScopeOutputValidationError(
            f"{label} has unexpected field(s): " + ", ".join(unexpected)
        )


def _path_from_file_entry(entry: Any) -> tuple[str, bool]:
    if isinstance(entry, str):
        return entry, False
    if isinstance(entry, dict):
        _reject_unexpected_keys(entry, allowed=PARTIAL_FILE_KEYS, label="partial file entry")
        path = entry.get("path")
        hunks = entry.get("hunks")
        if not isinstance(path, str) or not path:
            raise PrScopeOutputValidationError("partial file entries must have a non-empty 'path'")
        if (
            not isinstance(hunks, list)
            or not hunks
            or any(not isinstance(h, str) or not h for h in hunks)
        ):
            raise PrScopeOutputValidationError(
                "partial file entries must have a non-empty string 'hunks' list"
            )
        return path, True
    raise PrScopeOutputValidationError(
        "split file entries must be strings or {path, hunks} objects"
    )


def _validated_context_inputs(
    per_file: Any, excluded_paths: Any
) -> tuple[set[str], dict[str, int], set[str]]:
    if not isinstance(per_file, list):
        raise PrScopeOutputValidationError("per_file must be a list")
    if not isinstance(excluded_paths, list):
        raise PrScopeOutputValidationError("excluded_paths must be a list")

    changed_paths: set[str] = set()
    per_file_added: dict[str, int] = {}
    for index, entry in enumerate(per_file):
        label = f"per_file[{index}]"
        if not isinstance(entry, dict):
            raise PrScopeOutputValidationError(f"{label} must be an object")
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            raise PrScopeOutputValidationError(f"{label}.path must be a non-empty string")
        if path in changed_paths:
            raise PrScopeOutputValidationError(f"{label}.path duplicates an earlier per_file path")
        added = _require_non_negative_int(entry.get("added"), f"{label}.added")
        changed_paths.add(path)
        per_file_added[path] = added

    excluded_set: set[str] = set()
    for index, path in enumerate(excluded_paths):
        if not isinstance(path, str) or not path.strip():
            raise PrScopeOutputValidationError(
                f"excluded_paths[{index}] must be a non-empty string"
            )
        excluded_set.add(path)

    return changed_paths, per_file_added, excluded_set


def _remaining_paths(
    remaining: Any,
    *,
    changed_paths: set[str],
    excluded_set: set[str],
    split_whole_paths: set[str],
) -> set[str]:
    if not isinstance(remaining, list):
        raise PrScopeOutputValidationError(
            "request_split payload must include a 'remaining_in_original' list"
        )

    remaining_paths: set[str] = set()
    for entry in remaining:
        if not isinstance(entry, str) or not entry:
            raise PrScopeOutputValidationError(
                "remaining_in_original entries must be non-empty strings"
            )
        if entry in excluded_set:
            raise PrScopeOutputValidationError(
                f"excluded path '{entry}' cannot appear in remaining_in_original"
            )
        if entry not in changed_paths:
            raise PrScopeOutputValidationError(
                f"remaining_in_original path '{entry}' is not a changed file"
            )
        if entry in split_whole_paths:
            raise PrScopeOutputValidationError(
                f"path '{entry}' cannot appear in both a whole-file split and remaining_in_original"
            )
        if entry in remaining_paths:
            raise PrScopeOutputValidationError(
                f"path '{entry}' is listed more than once in remaining_in_original"
            )
        remaining_paths.add(entry)

    return remaining_paths


def validate_pr_scope_output(
    *,
    payload: dict[str, Any],
    per_file: list[dict[str, Any]],
    excluded_paths: list[str],
    new_loc_total: int,
) -> None:
    """Validate a gate payload against the deterministic changed-file partition."""

    if not isinstance(payload, dict):
        raise PrScopeOutputValidationError("payload must be an object")
    if payload.get("gate") != "pr-scope":
        raise PrScopeOutputValidationError("payload.gate must equal 'pr-scope'")

    _require_non_empty_string(payload.get("summary"), "payload.summary")
    verdict = payload.get("verdict")
    if verdict == "atomic":
        _reject_unexpected_keys(payload, allowed=ATOMIC_PAYLOAD_KEYS, label="atomic payload")
        return
    if verdict != "request_split":
        raise PrScopeOutputValidationError(
            f"payload.verdict must be 'atomic' or 'request_split' (got '{verdict}')"
        )
    _reject_unexpected_keys(
        payload, allowed=REQUEST_SPLIT_PAYLOAD_KEYS, label="request_split payload"
    )

    _require_non_negative_int(new_loc_total, "new_loc_total")

    changed_paths, per_file_added, excluded_set = _validated_context_inputs(
        per_file, excluded_paths
    )
    per_file_added_total = sum(per_file_added.values())
    if per_file_added_total != new_loc_total:
        raise PrScopeOutputValidationError(
            "new_loc_total must equal the sum of per_file added LOC "
            f"({new_loc_total} != {per_file_added_total})"
        )

    splits = payload.get("splits")
    remaining = payload.get("remaining_in_original")
    if not isinstance(splits, list) or not splits:
        raise PrScopeOutputValidationError(
            "request_split payload must include a non-empty 'splits' list"
        )
    if len(splits) > MAX_SPLITS:
        raise PrScopeOutputValidationError(
            f"request_split payload must not include more than {MAX_SPLITS} splits"
        )

    split_whole_paths: set[str] = set()
    split_partial_paths: set[str] = set()
    split_names: set[str] = set()
    saw_partial = False
    estimated_total = 0

    for split in splits:
        if not isinstance(split, dict):
            raise PrScopeOutputValidationError("each split must be an object")
        _reject_unexpected_keys(split, allowed=SPLIT_KEYS, label="split")
        name = _require_non_empty_string(split.get("name"), "split.name")
        if name in split_names:
            raise PrScopeOutputValidationError(f"split.name '{name}' is duplicated")
        split_names.add(name)

    for split in splits:
        name = _require_non_empty_string(split.get("name"), "split.name")
        _require_non_empty_string(split.get("rationale"), "split.rationale")
        files = split.get("files")
        if not isinstance(files, list) or not files:
            raise PrScopeOutputValidationError("each split must include a non-empty 'files' list")
        estimated = _require_non_negative_int(
            split.get("estimated_new_loc"), "split.estimated_new_loc"
        )
        depends_on = split.get("depends_on")
        if "depends_on" in split and (
            not isinstance(depends_on, list)
            or any(not isinstance(item, str) or not item for item in depends_on)
        ):
            raise PrScopeOutputValidationError(
                "split.depends_on must be a list of non-empty strings when present"
            )
        if isinstance(depends_on, list):
            for dependency in depends_on:
                if dependency == name:
                    raise PrScopeOutputValidationError(
                        f"split.depends_on for '{name}' cannot reference itself"
                    )
                if dependency not in split_names:
                    raise PrScopeOutputValidationError(
                        f"split.depends_on references unknown split '{dependency}'"
                    )
        estimated_total += estimated
        split_has_partial = False

        for file_entry in files:
            path, is_partial = _path_from_file_entry(file_entry)
            if path in excluded_set:
                raise PrScopeOutputValidationError(
                    f"excluded path '{path}' cannot appear in a split"
                )
            if path not in changed_paths:
                raise PrScopeOutputValidationError(f"split path '{path}' is not a changed file")
            if is_partial:
                saw_partial = True
                if path in split_whole_paths:
                    raise PrScopeOutputValidationError(
                        f"path '{path}' cannot be both whole-file and partial-file assigned"
                    )
                if path in split_partial_paths:
                    raise PrScopeOutputValidationError(
                        f"path '{path}' is assigned more than once across splits"
                    )
                split_has_partial = True
                split_partial_paths.add(path)
                continue
            if path in split_whole_paths or path in split_partial_paths:
                raise PrScopeOutputValidationError(
                    f"path '{path}' is assigned more than once across splits"
                )
            split_whole_paths.add(path)
        if split_has_partial and estimated == 0:
            raise PrScopeOutputValidationError(
                "partial-file splits must have positive estimated_new_loc"
            )

    remaining_paths = _remaining_paths(
        remaining,
        changed_paths=changed_paths,
        excluded_set=excluded_set,
        split_whole_paths=split_whole_paths,
    )

    if split_partial_paths - remaining_paths:
        missing_remainders = sorted(split_partial_paths - remaining_paths)
        raise PrScopeOutputValidationError(
            "partial-file split paths must also remain in remaining_in_original: "
            + ", ".join(missing_remainders)
        )

    covered_paths = split_whole_paths | split_partial_paths | remaining_paths
    missing_paths = changed_paths - covered_paths
    if missing_paths:
        raise PrScopeOutputValidationError(
            "request_split payload is missing changed files: " + ", ".join(sorted(missing_paths))
        )

    if not saw_partial:
        remaining_total = sum(per_file_added[path] for path in remaining_paths)
        if estimated_total + remaining_total != new_loc_total:
            raise PrScopeOutputValidationError(
                "estimated_new_loc total plus remaining added LOC must equal new_loc_total "
                f"({estimated_total} + {remaining_total} != {new_loc_total})"
            )
        return

    whole_in_splits_total = sum(per_file_added[path] for path in split_whole_paths)
    partial_remaining_upper = sum(per_file_added[path] for path in split_partial_paths)
    total_moved = estimated_total - whole_in_splits_total
    moved_upper = math.floor(partial_remaining_upper * 1.05)
    if total_moved <= 0:
        raise PrScopeOutputValidationError(
            "estimated_new_loc total implies whole-file splits exceed their actual LOC "
            f"(estimated_total={estimated_total}, whole-file LOC={whole_in_splits_total})"
        )
    if total_moved > moved_upper:
        raise PrScopeOutputValidationError(
            "estimated_new_loc total for partial-file splits exceeds the partials' total LOC "
            f"(implied moved={total_moved}, partial LOC max={moved_upper})"
        )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-file-json")
    parser.add_argument("--per-file-json-file")
    parser.add_argument("--excluded-paths-json")
    parser.add_argument("--excluded-paths-json-file")
    parser.add_argument("--new-loc-total", required=True, type=int)
    args = parser.parse_args(argv)

    try:
        payload = json.load(sys.stdin)
        per_file = load_json_or_file(
            inline=args.per_file_json,
            file_path=args.per_file_json_file,
            label="per-file",
            flag_stem="per-file",
            error_cls=PrScopeOutputValidationError,
        )
        excluded_paths = load_json_or_file(
            inline=args.excluded_paths_json,
            file_path=args.excluded_paths_json_file,
            label="excluded-paths",
            flag_stem="excluded-paths",
            error_cls=PrScopeOutputValidationError,
        )
        validate_pr_scope_output(
            payload=payload,
            per_file=per_file,
            excluded_paths=excluded_paths,
            new_loc_total=args.new_loc_total,
        )
        return 0
    except (json.JSONDecodeError, PrScopeOutputValidationError) as exc:
        print(f"validate_pr_scope_output: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(_main())
