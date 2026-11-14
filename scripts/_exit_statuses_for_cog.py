"""Helper imported by the cog snippet in README.md to render the
"Loop statuses" table.

Loads the canonical enum from templates/state.schema.json and the
description map from templates/exit_statuses.yaml, validates that the
two key sets match exactly, and returns ordered (status, description)
tuples.

Order is the YAML file's order — reordering the table is a one-file
edit (the YAML), not a generator change.

Mirrors the shape of scripts/_personas_for_cog.py: short module that
adds scripts/ to sys.path on import so cog can find it from anywhere
the orchestrator invokes cog from.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_REPO_ROOT = _SCRIPTS.parent
_SCHEMA = _REPO_ROOT / "templates" / "state.schema.json"
_MANIFEST = _REPO_ROOT / "templates" / "exit_statuses.yaml"


class ExitStatusManifestError(ValueError):
    """Raised when the YAML key set drifts from the schema enum."""


def _load_enum() -> set[str]:
    data = json.loads(_SCHEMA.read_text())
    try:
        enum = data["properties"]["status"]["enum"]
    except (KeyError, TypeError) as e:
        raise ExitStatusManifestError(f"could not find properties.status.enum in {_SCHEMA}") from e
    if not isinstance(enum, list) or not all(isinstance(v, str) for v in enum):
        raise ExitStatusManifestError(
            f"{_SCHEMA}: properties.status.enum must be a list of strings"
        )
    return set(enum)


def _load_yaml() -> list[tuple[str, str]]:
    data = yaml.safe_load(_MANIFEST.read_text())
    if not isinstance(data, dict):
        raise ExitStatusManifestError(f"{_MANIFEST}: top level must be a mapping")
    statuses = data.get("statuses")
    if not isinstance(statuses, dict) or not statuses:
        raise ExitStatusManifestError(f"{_MANIFEST}: 'statuses' must be a non-empty mapping")
    pairs: list[tuple[str, str]] = []
    for key, value in statuses.items():
        if not isinstance(key, str):
            raise ExitStatusManifestError(
                f"{_MANIFEST}: status key must be a string, got {type(key).__name__}"
            )
        if not isinstance(value, str) or not value.strip():
            raise ExitStatusManifestError(
                f"{_MANIFEST}: description for {key!r} must be a non-empty string"
            )
        pairs.append((key, value.strip()))
    return pairs


def statuses() -> list[tuple[str, str]]:
    """Return ordered (status, description) tuples for the cog snippet.

    Validates that the YAML key set matches the schema enum exactly;
    raises ExitStatusManifestError on drift so cog surfaces the error
    rather than silently rendering a partial table.
    """
    enum = _load_enum()
    pairs = _load_yaml()
    yaml_keys = {k for k, _ in pairs}
    missing = enum - yaml_keys
    extra = yaml_keys - enum
    if missing or extra:
        msg_parts = []
        if missing:
            msg_parts.append(f"missing from YAML: {sorted(missing)}")
        if extra:
            msg_parts.append(f"not in schema enum: {sorted(extra)}")
        raise ExitStatusManifestError(
            f"templates/exit_statuses.yaml key set does not match "
            f"templates/state.schema.json status.enum ({'; '.join(msg_parts)})"
        )
    return pairs
