#!/usr/bin/env python3
"""Validate skill metadata and JSON schema files.

Checks:
  1. SKILL.md has YAML frontmatter with non-empty `name`, `version`,
     and `description` keys. `version` must be a semver string
     (e.g. 0.1.0). (AGENTS.md is a Codex-style plain markdown file
     and is intentionally not frontmatter-validated.)
  2. templates/state.schema.json is valid JSON and a valid JSON Schema.

Exits non-zero on any failure with a clear message.
"""

import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
errors: list[str] = []

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def check_frontmatter(path: Path) -> None:
    text = path.read_text()
    if not text.startswith("---\n"):
        errors.append(f"{path}: missing leading '---' frontmatter")
        return
    end = text.find("\n---\n", 4)
    if end == -1:
        errors.append(f"{path}: unterminated frontmatter")
        return
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError as e:
        errors.append(f"{path}: YAML parse error: {e}")
        return
    if not isinstance(data, dict):
        errors.append(f"{path}: frontmatter is not a YAML mapping")
        return
    for key in ("name", "version", "description"):
        if not data.get(key):
            errors.append(f"{path}: missing or empty '{key}'")
    version = data.get("version")
    if version is not None and not (isinstance(version, str) and SEMVER_RE.match(version)):
        errors.append(f"{path}: 'version' must be a semver string like '0.1.0', got {version!r}")


def check_schema(path: Path) -> None:
    try:
        schema = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        errors.append(f"{path}: invalid JSON: {e}")
        return
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as e:
        errors.append(f"{path}: invalid JSON Schema: {e}")


check_frontmatter(REPO / "SKILL.md")
check_schema(REPO / "templates/state.schema.json")

if errors:
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
print("metadata ok")
