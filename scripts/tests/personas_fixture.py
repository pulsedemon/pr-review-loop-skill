"""personas.yaml writer shared by the generator tests."""

from collections.abc import Collection
from pathlib import Path


def write_personas_yaml(
    tmp_path: Path,
    panel: list[str],
    carriers: Collection[str] = (),
    flag: str = "move_c",
    *,
    owner_index: int = 0,
) -> Path:
    """owner_index is the zero-based position of the schema owner in panel."""
    lines = ["panel:"]
    for index, name in enumerate(panel):
        lines.extend([f"  - name: {name}", f"    description: {name} persona"])
        if name in carriers:
            lines.append(f"    {flag}: true")
        if index == owner_index:
            lines.append("    owns_schema_constraint_blocker: true")
    lines.extend(
        [
            "adversary:",
            "  name: adversary",
            "  description: adversary persona",
            "addendums: []",
        ]
    )
    path = tmp_path / "personas.yaml"
    path.write_text("\n".join(lines) + "\n")
    return path
