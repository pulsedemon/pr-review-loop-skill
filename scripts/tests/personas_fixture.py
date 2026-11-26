"""personas.yaml writer shared by the generator tests."""

from collections.abc import Collection
from pathlib import Path

import yaml


def write_personas_yaml(
    tmp_path: Path,
    panel: list[str],
    carriers: Collection[str] = (),
    flag: str = "move_c",
    *,
    owner_index: int = 0,
) -> Path:
    """owner_index is the zero-based position of the schema owner in panel."""
    entries = []
    for index, name in enumerate(panel):
        entry: dict[str, str | bool] = {"name": name, "description": f"{name} persona"}
        if name in carriers:
            entry[flag] = True
        if index == owner_index:
            entry["owns_schema_constraint_blocker"] = True
        entries.append(entry)
    manifest = {
        "panel": entries,
        "adversary": {"name": "adversary", "description": "adversary persona"},
        "addendums": [],
    }
    path = tmp_path / "personas.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return path
