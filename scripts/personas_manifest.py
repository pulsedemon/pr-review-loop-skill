"""Persona manifest loader.

Source of truth: reviewers/personas.yaml. Every sync test consumes
derived lists from here so a single edit to the manifest tells every
dependent surface what to update.

Used as a module (`from scripts.personas_manifest import load_manifest`)
and as a CLI for bats tests (`python3 scripts/personas_manifest.py --list X`).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ManifestError(ValueError):
    """Raised when reviewers/personas.yaml is malformed or internally inconsistent."""


_PANEL_KEYS = frozenset(
    {
        "name",
        "description",
        "move_a",
        "move_a1",
        "move_b",
        "move_c",
        "owns_schema_constraint_blocker",
    }
)
_ADVERSARY_KEYS = frozenset({"name", "description"})
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Persona:
    name: str
    description: str
    move_a: bool = False
    move_a1: bool = False
    move_b: bool = False
    move_c: bool = False
    owns_schema_constraint_blocker: bool = False

    @property
    def file(self) -> str:
        return f"{self.name}.md"


@dataclass(frozen=True)
class Manifest:
    panel: tuple[Persona, ...]
    adversary: Persona
    addendums: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.panel:
            raise ManifestError("manifest panel must be non-empty")
        seen: set[str] = set()
        for p in self.panel:
            if p.name in seen:
                raise ManifestError(f"duplicate panel persona name: {p.name}")
            seen.add(p.name)
        owners = sum(1 for p in self.panel if p.owns_schema_constraint_blocker)
        if owners != 1:
            raise ManifestError(
                f"exactly one panel persona must set owns_schema_constraint_blocker, got {owners}"
            )
        # Unreachable from YAML: _ADVERSARY_KEYS rejects every move key as
        # unknown before construction. This catches direct Persona() building.
        if self.adversary.owns_schema_constraint_blocker or any(
            (
                self.adversary.move_a,
                self.adversary.move_a1,
                self.adversary.move_b,
                self.adversary.move_c,
            )
        ):
            raise ManifestError(
                f"adversary {self.adversary.name!r} must not set a move flag or "
                f"owns_schema_constraint_blocker"
            )
        panel_files = {p.file for p in self.panel} | {self.adversary.file}
        collisions = panel_files & set(self.addendums)
        if collisions:
            raise ManifestError(
                f"addendums collide with panel/adversary filenames: {sorted(collisions)}"
            )

    def move_a_personas(self) -> list[Persona]:
        return [p for p in self.panel if p.move_a]

    def move_a1_personas(self) -> list[Persona]:
        return [p for p in self.panel if p.move_a1]

    def move_b_personas(self) -> list[Persona]:
        return [p for p in self.panel if p.move_b]

    def move_c_personas(self) -> list[Persona]:
        return [p for p in self.panel if p.move_c]

    def schema_constraint_owner(self) -> Persona:
        # __post_init__ guarantees exactly one owner; StopIteration here would
        # mean someone bypassed dataclass construction.
        return next(p for p in self.panel if p.owns_schema_constraint_blocker)


def _parse_persona(path: Path, label: str, raw: object, allowed_keys: frozenset[str]) -> Persona:
    if not isinstance(raw, dict):
        raise ManifestError(f"{path}: {label} must be a mapping, got {type(raw).__name__}")
    if "name" not in raw:
        raise ManifestError(f"{path}: {label} missing required key 'name'")
    extra = set(raw.keys()) - allowed_keys
    if extra:
        raise ManifestError(
            f"{path}: {label} has unknown key(s): {sorted(extra)} "
            f"(typo? allowed: {sorted(allowed_keys)})"
        )
    name = raw["name"]
    if not isinstance(name, str):
        raise ManifestError(f"{path}: {label} 'name' must be a string, got {type(name).__name__}")
    if not _NAME_RE.match(name):
        raise ManifestError(
            f"{path}: {label}: 'name' {name!r} must match {_NAME_RE.pattern} "
            f"(lowercase identifier; constrains downstream filename + schema enum splice)"
        )
    if "description" not in raw:
        raise ManifestError(f"{path}: {label} {name!r}: missing required key 'description'")
    description = raw["description"]
    if not isinstance(description, str):
        raise ManifestError(
            f"{path}: {label} {name!r}: 'description' must be a string, "
            f"got {type(description).__name__}"
        )
    description = description.strip()
    if not description:
        raise ManifestError(f"{path}: {label} {name!r}: 'description' must be non-empty")
    if description.startswith("-"):
        raise ManifestError(
            f"{path}: {label} {name!r}: 'description' must not start with '-' "
            f"(generator prepends the bullet)"
        )
    moves: dict[str, bool] = {}
    for key in ("move_a", "move_a1", "move_b", "move_c"):
        value = raw.get(key, False)
        if not isinstance(value, bool):
            raise ManifestError(
                f"{path}: {label} {name!r}: {key!r} must be a boolean, got {type(value).__name__}"
            )
        moves[key] = value
    owns = raw.get("owns_schema_constraint_blocker", False)
    if not isinstance(owns, bool):
        raise ManifestError(
            f"{path}: {label} {name!r}: 'owns_schema_constraint_blocker' must be a boolean, "
            f"got {type(owns).__name__}"
        )
    return Persona(
        name=name,
        description=description,
        owns_schema_constraint_blocker=owns,
        **moves,
    )


def load_manifest(path: Path) -> Manifest:
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError) as e:
        raise ManifestError(f"failed to read {path}: {e}") from e
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ManifestError(f"failed to parse {path}: {e}") from e
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: top level must be a mapping")
    panel_raw = data.get("panel")
    adv_raw = data.get("adversary")
    add_raw = data.get("addendums", [])
    if not isinstance(panel_raw, list) or not panel_raw:
        raise ManifestError(f"{path}: 'panel' must be a non-empty list")
    if not isinstance(adv_raw, dict):
        raise ManifestError(f"{path}: 'adversary' must be a mapping")
    if not isinstance(add_raw, list):
        raise ManifestError(f"{path}: 'addendums' must be a list")
    panel: list[Persona] = []
    for i, p in enumerate(panel_raw):
        panel.append(_parse_persona(path, f"panel[{i}]", p, _PANEL_KEYS))
    adversary = _parse_persona(path, "adversary", adv_raw, _ADVERSARY_KEYS)
    addendums_list: list[str] = []
    for i, a in enumerate(add_raw):
        if not isinstance(a, str):
            raise ManifestError(f"{path}: addendums[{i}] must be a string, got {type(a).__name__}")
        addendums_list.append(a)
    return Manifest(panel=tuple(panel), adversary=adversary, addendums=tuple(addendums_list))


def _default_manifest_path() -> Path:
    return Path(__file__).resolve().parents[1] / "reviewers" / "personas.yaml"


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Persona manifest CLI for bats consumers.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_default_manifest_path(),
        help="path to personas.yaml (default: reviewers/personas.yaml)",
    )
    parser.add_argument(
        "--list",
        choices=[
            "panel-names",
            "panel-files",
            "move-a-names",
            "move-a1-names",
            "move-b-names",
            "move-c-names",
            "move-c-files",
            "addendums",
            "schema-constraint-owner",
            "all-known-files",
        ],
        required=True,
        help="which derived list to print, one item per line",
    )
    args = parser.parse_args(argv)
    # reserve exit 2 for argparse usage errors.
    try:
        m = load_manifest(args.manifest)
    except ManifestError as e:
        print(f"manifest error: {e}", file=sys.stderr)
        return 3
    if args.list == "panel-names":
        for p in m.panel:
            print(p.name)
    elif args.list == "panel-files":
        for p in m.panel:
            print(p.file)
    elif args.list == "move-a-names":
        for p in m.move_a_personas():
            print(p.name)
    elif args.list == "move-a1-names":
        for p in m.move_a1_personas():
            print(p.name)
    elif args.list == "move-b-names":
        for p in m.move_b_personas():
            print(p.name)
    elif args.list == "move-c-names":
        for p in m.move_c_personas():
            print(p.name)
    elif args.list == "move-c-files":
        for p in m.move_c_personas():
            print(p.file)
    elif args.list == "addendums":
        for a in m.addendums:
            print(a)
    elif args.list == "schema-constraint-owner":
        print(m.schema_constraint_owner().name)
    elif args.list == "all-known-files":
        for p in m.panel:
            print(p.file)
        print(m.adversary.file)
        for a in m.addendums:
            print(a)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
