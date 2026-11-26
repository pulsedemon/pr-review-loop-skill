"""exercise each generated move with a manifest carrying only that flag."""

from __future__ import annotations

from pathlib import Path

import _move_c_bullet_for_cog  # type: ignore[import-not-found]
import pytest
from _move_c_bullet_for_cog import render  # type: ignore[import-not-found]
from personas_fixture import write_personas_yaml  # type: ignore[import-not-found]
from personas_manifest import ManifestError  # type: ignore[import-not-found]


def test_renders_only_move_c_personas(tmp_path: Path) -> None:
    yaml_path = write_personas_yaml(
        tmp_path,
        ["alpha", "beta", "gamma"],
        carriers=["alpha", "gamma"],
    )
    out = render(yaml_path)
    assert out.startswith("- **Move C (cross-doc consistency)**, `alpha`, `gamma`:")


def test_omits_adversary_even_if_named_in_panel(tmp_path: Path) -> None:
    """Per docs/procedure-moves.md: adversary is excluded from move_c by
    design. The manifest's __post_init__ already forbids the adversary
    record from setting move_c: true, so the only way `adversary` could
    appear in the rendered list is if a panel entry happened to be named
    `adversary`. The renderer must skip that defensively.
    """
    yaml_path = write_personas_yaml(
        tmp_path,
        ["alpha", "adversary"],
        carriers=["alpha", "adversary"],
    )
    out = render(yaml_path)
    assert "adversary" not in out
    assert "alpha" in out


def test_no_bullet_when_no_persona_carries_the_move(tmp_path: Path) -> None:
    """A move nobody carries renders nothing, not a bullet with an empty list."""
    yaml_path = write_personas_yaml(
        tmp_path,
        ["alpha"],
    )
    out = render(yaml_path)
    # This fixture sets no move flag at all, so all four bullets drop out.
    assert out == ""


def test_only_the_carried_moves_render(tmp_path: Path) -> None:
    """Move C is carried here; A/A.1/B are not, so only Move C appears."""
    yaml_path = write_personas_yaml(
        tmp_path,
        ["alpha"],
        carriers=["alpha"],
    )
    out = render(yaml_path)
    assert "- **Move C" in out
    for absent in ("- **Move A (", "- **Move A.1", "- **Move B"):
        assert absent not in out
    assert "**, :" not in out


def test_default_manifest_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write_personas_yaml(tmp_path, ["alpha"], carriers=["alpha"])
    monkeypatch.setattr(_move_c_bullet_for_cog, "_DEFAULT_MANIFEST", path)
    assert render().startswith("- **Move C (cross-doc consistency)**, `alpha` only:")


def test_move_c_sorts_carriers_and_names_the_configured_schema_owner(tmp_path: Path) -> None:
    manifest = write_personas_yaml(
        tmp_path, ["zeta", "requirements", "alpha"], carriers=["zeta", "alpha"], owner_index=1
    )
    out = render(manifest)
    assert "cross-reference `requirements` in `detail`" in out
    assert "`requirements` owns the blocker" in out
    assert out.startswith("- **Move C (cross-doc consistency)**, `alpha`, `zeta`:")


def test_load_manifest_failure_propagates(tmp_path: Path) -> None:
    bad = tmp_path / "personas.yaml"
    bad.write_text(
        "adversary:\n  name: adversary\n  description: adversary persona\naddendums: []\n"
    )
    with pytest.raises(ManifestError, match="'panel' must be a non-empty list"):
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
    yaml_path = write_personas_yaml(tmp_path, ["alpha"], carriers=["alpha"], flag=flag)
    out = render(yaml_path)
    assert out.startswith(heading), out
    assert out.count("\n") == 0, "exactly one bullet expected"
    assert "`alpha` only" in out


def test_move_a1_bullet_carries_the_enum_region(tmp_path: Path) -> None:
    """The nested regen:move-a1-enum markers survive cog rendering.

    regen_move_a1_enum.py rewrites between these markers after cog runs;
    losing them would silently freeze the enum at whatever cog emitted.
    """
    yaml_path = write_personas_yaml(tmp_path, ["alpha"], carriers=["alpha"], flag="move_a1")
    out = render(yaml_path)
    assert "<!-- regen:move-a1-enum:start -->" in out
    assert "<!-- regen:move-a1-enum:end -->" in out
    start = out.index("<!-- regen:move-a1-enum:start -->")
    end = out.index("<!-- regen:move-a1-enum:end -->")
    assert out[start:end].count("`") >= 2, "enum region must carry backticked values"
    assert "`move_a1_pattern`" in out


def test_move_b_bullet_carries_the_pattern_marker(tmp_path: Path) -> None:
    yaml_path = write_personas_yaml(tmp_path, ["alpha"], carriers=["alpha"], flag="move_b")
    out = render(yaml_path)
    assert "`move_b_pattern:" in out


def test_multiple_carriers_render_a_sorted_comma_list(tmp_path: Path) -> None:
    """More than one carrier drops the `x` only phrasing and sorts."""
    yaml_path = write_personas_yaml(
        tmp_path,
        ["zeta", "alpha"],
        carriers=["zeta", "alpha"],
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
    yaml_path = write_personas_yaml(tmp_path, ["alpha"], carriers=["alpha"], flag="move_a1")
    out = render(yaml_path)
    assert "via one of three sub-mechanics" in out
    assert (
        "<!-- regen:move-a1-enum:start -->`first`, `second`, `third`<!-- regen:move-a1-enum:end -->"
        in out
    )
