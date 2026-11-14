"""Shared loader for CLI args that accept inline JSON or a path to a JSON file.

Both `scripts/validate_pr_scope_output.py` and `scripts/pr_scope_step.py` expose
multiple JSON-bearing CLI args. For pathologically large payloads (e.g. a
PR-scope record carrying `per_file` for thousands of changed files), the inline
form risks exceeding OS `ARG_MAX` limits. Each `--foo-json` flag therefore has
a `--foo-json-file` companion that reads the same JSON from disk; this helper
enforces the mutex and preserves the long-standing
`failed to parse <label> JSON (...)` wording so existing CLI tests stay green
regardless of which input mode the caller picks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_or_file(
    *,
    inline: str | None,
    file_path: str | None,
    label: str,
    flag_stem: str,
    error_cls: type[Exception],
    required: bool = True,
) -> Any:
    """Parse JSON from either an inline string or a file path.

    `inline` and `file_path` are mutually exclusive. When `required` is True,
    exactly one must be provided. When `required` is False, both may be None
    and the helper returns None.

    `label` is the human-readable noun used in parse-error messages (matches
    the wording from the pre-helper inline-only call sites). `flag_stem` is
    the CLI flag stem used in mutex / missing-input errors so the message
    names the actual flags the caller can fix.
    """
    if inline is not None and file_path is not None:
        raise error_cls(f"--{flag_stem}-json and --{flag_stem}-json-file are mutually exclusive")
    if inline is None and file_path is None:
        if required:
            raise error_cls(f"one of --{flag_stem}-json or --{flag_stem}-json-file is required")
        return None

    if file_path is not None:
        try:
            raw = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise error_cls(f"failed to read {label} JSON file ({exc})") from exc
    else:
        assert inline is not None
        raw = inline

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise error_cls(f"failed to parse {label} JSON ({exc})") from exc
