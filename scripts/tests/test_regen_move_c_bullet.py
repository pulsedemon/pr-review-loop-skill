"""exercise each generated move with a manifest carrying only that flag."""

from __future__ import annotations

from pathlib import Path

import _move_c_bullet_for_cog  # type: ignore[import-not-found]
import pytest
from _move_c_bullet_for_cog import render  # type: ignore[import-not-found]
from personas_manifest import ManifestError  # type: ignore[import-not-found]


def _write_manifest(
    tmp_path: Path,
    panel: list[tuple[str, bool]],
    adversary_name: str = "adversary",
    flag: str = "move_c",
) -> Path:
    """Build a minimal-valid personas.yaml fixture.

    `panel` is a list of (name, carries) tuples, where `carries` sets the
    move named by `flag`. Exactly one entry is given
    `owns_schema_constraint_blocker: true` (manifest invariant).
    """
    lines = ["panel:"]
    for i, (name, carries) in enumerate(panel):
        owns = "true" if i == 0 else "false"
        lines.append(f"  - name: {name}")
        lines.append(f"    file: {name}.md")
        lines.append(f"    description: {name} persona")
        lines.append(f"    {flag}: {'true' if carries else 'false'}")
        lines.append(f"    owns_schema_constraint_blocker: {owns}")
    lines.append("adversary:")
    lines.append(f"  name: {adversary_name}")
    lines.append(f"  file: {adversary_name}.md")
    lines.append(f"  description: {adversary_name} persona")
    lines.append("addendums: []")
    p = tmp_path / "personas.yaml"
    p.write_text("\n".join(lines) + "\n")
    return p


def test_renders_only_move_c_personas(tmp_path: Path) -> None:
    yaml_path = _write_manifest(
        tmp_path,
        [("alpha", True), ("beta", False), ("gamma", True)],
    )
    out = render(yaml_path)
    assert "alpha" in out
    assert "gamma" in out
    assert "beta" not in out


def test_omits_adversary_even_if_named_in_panel(tmp_path: Path) -> None:
    """Per docs/procedure-moves.md: adversary is excluded from move_c by
    design. The manifest's __post_init__ already forbids the adversary
    record from setting move_c: true, so the only way `adversary` could
    appear in the rendered list is if a panel entry happened to be named
    `adversary`. The renderer must skip that defensively.
    """
    yaml_path = _write_manifest(
        tmp_path,
        [("alpha", True), ("adversary", True)],
    )
    out = render(yaml_path)
    assert "adversary" not in out
    assert "alpha" in out


def test_alphabetical_order(tmp_path: Path) -> None:
    yaml_path = _write_manifest(
        tmp_path,
        [("zeta", True), ("alpha", True)],
    )
    out = render(yaml_path)
    assert out.index("alpha") < out.index("zeta")


def test_no_bullet_when_no_persona_carries_the_move(tmp_path: Path) -> None:
    """A move nobody carries renders nothing, not a bullet with an empty list."""
    yaml_path = _write_manifest(
        tmp_path,
        [("alpha", False)],
    )
    out = render(yaml_path)
    # This fixture sets no move flag at all, so all four bullets drop out.
    assert out == ""


def test_only_the_carried_moves_render(tmp_path: Path) -> None:
    """Move C is carried here; A/A.1/B are not, so only Move C appears."""
    yaml_path = _write_manifest(
        tmp_path,
        [("alpha", True)],
    )
    out = render(yaml_path)
    assert "- **Move C" in out
    for absent in ("- **Move A (", "- **Move A.1", "- **Move B"):
        assert absent not in out
    assert "**, :" not in out


def test_default_manifest_path() -> None:
    """Calling render() with no argument uses the real personas.yaml."""
    out = render()
    assert out
    assert "Move C" in out


def test_move_c_uses_the_configured_schema_constraint_owner(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, [("requirements", True), ("type_design", False)])
    out = render(manifest)
    assert "cross-reference `requirements` in `detail`" in out
    assert "`requirements` owns the blocker" in out
    assert "`type_design`" not in out


def test_load_manifest_failure_propagates(tmp_path: Path) -> None:
    """If the manifest is malformed, render must surface the loader error
    rather than swallowing it. A missing 'panel' key is the simplest
    trigger."""
    bad = tmp_path / "personas.yaml"
    bad.write_text("adversary:\n  name: x\n")
    with pytest.raises(ManifestError):
        render(bad)


@pytest.mark.parametrize(
    ("flag", "heading"),
    [
        ("move_a", "- **Move A (test-intent audit)**, "),
        ("move_a1", "- **Move A.1 (assertion-vacuity audit)**, "),
        ("move_b", "- **Move B (second-instance sweep)**, "),
        ("move_c", "- **Move C (cross-doc consistency)**, "),
    ],
)
def test_each_flag_renders_only_its_own_bullet(tmp_path: Path, flag: str, heading: str) -> None:
    """Each move_* flag maps to its own template and nothing else."""
    yaml_path = _write_manifest(tmp_path, [("alpha", True)], flag=flag)
    out = render(yaml_path)
    assert out.startswith(heading), out
    assert out.count("\n") == 0, "exactly one bullet expected"
    assert "`alpha` only" in out


def test_move_a1_bullet_carries_the_enum_region(tmp_path: Path) -> None:
    """The nested regen:move-a1-enum markers survive cog rendering.

    regen_move_a1_enum.py rewrites between these markers after cog runs;
    losing them would silently freeze the enum at whatever cog emitted.
    """
    yaml_path = _write_manifest(tmp_path, [("alpha", True)], flag="move_a1")
    out = render(yaml_path)
    assert "<!-- regen:move-a1-enum:start -->" in out
    assert "<!-- regen:move-a1-enum:end -->" in out
    start = out.index("<!-- regen:move-a1-enum:start -->")
    end = out.index("<!-- regen:move-a1-enum:end -->")
    assert out[start:end].count("`") >= 2, "enum region must carry backticked values"
    assert "`move_a1_pattern`" in out


def test_move_b_bullet_carries_the_pattern_marker(tmp_path: Path) -> None:
    yaml_path = _write_manifest(tmp_path, [("alpha", True)], flag="move_b")
    out = render(yaml_path)
    assert "`move_b_pattern:" in out


def test_multiple_carriers_render_a_sorted_comma_list(tmp_path: Path) -> None:
    """More than one carrier drops the `x` only phrasing and sorts."""
    yaml_path = _write_manifest(
        tmp_path,
        [("zeta", True), ("alpha", True)],
        flag="move_b",
    )
    out = render(yaml_path)
    assert "**, `alpha`, `zeta`:" in out
    assert "only" not in out


def test_move_a1_sub_mechanic_count_is_derived_not_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The count word tracks the enum length, so prose cannot drift from it."""
    enum_manifest = tmp_path / "move-a1-enum.yaml"
    enum_manifest.write_text("move_a1_pattern:\n  - first\n  - second\n  - third\n")
    monkeypatch.setattr(_move_c_bullet_for_cog, "_A1_ENUM_MANIFEST", enum_manifest)
    yaml_path = _write_manifest(tmp_path, [("alpha", True)], flag="move_a1")
    out = render(yaml_path)
    assert "via one of three sub-mechanics" in out
    assert (
        "<!-- regen:move-a1-enum:start -->`first`, `second`, `third`<!-- regen:move-a1-enum:end -->"
        in out
    )
