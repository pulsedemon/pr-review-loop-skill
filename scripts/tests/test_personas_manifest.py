"""tests for the persona-manifest loader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml
from personas_manifest import (  # type: ignore[import-not-found]  # sibling module made importable by conftest.py
    Manifest,
    ManifestError,
    Persona,
    _main,
    load_manifest,
)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "personas.yaml"
    p.write_text(textwrap.dedent(body).lstrip("\n"))
    return p


_MINIMAL_VALID = """
panel:
  - name: alpha
    description: alpha persona
    owns_schema_constraint_blocker: true
adversary:
  name: adversary
  description: adversary persona
addendums: []
"""


def test_load_real_manifest_succeeds() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = load_manifest(repo_root / "reviewers" / "personas.yaml")
    assert isinstance(manifest, Manifest)
    assert len(manifest.panel) >= 1
    assert manifest.adversary.name == "adversary"


def test_panel_persona_basic_fields(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            move_c: false
          - name: beta
            description: beta persona
            move_c: true
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    m = load_manifest(p)
    assert [x.name for x in m.panel] == ["alpha", "beta"]
    assert m.panel[1].owns_schema_constraint_blocker is True
    assert m.panel[0].owns_schema_constraint_blocker is False


def test_duplicate_panel_names_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            move_c: false
            owns_schema_constraint_blocker: true
          - name: alpha
            description: alpha duplicate
            move_c: false
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"duplicate panel persona name: alpha"):
        load_manifest(p)


def test_exactly_one_schema_constraint_owner_required(tmp_path: Path) -> None:
    p_zero = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            move_c: false
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"exactly one.*owns_schema_constraint_blocker.*got 0"):
        load_manifest(p_zero)


def test_more_than_one_schema_constraint_owner_rejected(tmp_path: Path) -> None:
    p_two = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            move_c: false
            owns_schema_constraint_blocker: true
          - name: beta
            description: beta persona
            move_c: false
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"exactly one.*owns_schema_constraint_blocker.*got 2"):
        load_manifest(p_two)


def test_move_c_personas_selects_multiple_carriers(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            move_c: true
          - name: beta
            description: beta persona
            move_c: false
            owns_schema_constraint_blocker: true
          - name: gamma
            description: gamma persona
            move_c: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    m = load_manifest(p)
    assert [x.name for x in m.move_c_personas()] == ["alpha", "gamma"]


def test_schema_constraint_owner_helper(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            move_c: false
            owns_schema_constraint_blocker: true
          - name: beta
            description: beta persona
            move_c: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    m = load_manifest(p)
    owner = m.schema_constraint_owner()
    assert isinstance(owner, Persona)
    assert owner.name == "alpha"


def test_non_dict_panel_entry_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - "not a dict"
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"panel\[0\] must be a mapping"):
        load_manifest(p)


def test_panel_entry_missing_required_key_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - description: alpha persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"panel\[0\] missing required key 'name'"):
        load_manifest(p)


def test_missing_manifest_file_raises_manifest_error(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does_not_exist.yaml"
    with pytest.raises(ManifestError, match=r"failed to read"):
        load_manifest(nonexistent)


def test_top_level_not_mapping_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, "- alpha\n- beta\n")
    with pytest.raises(ManifestError, match=r"top level must be a mapping"):
        load_manifest(p)


def test_panel_missing_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"'panel' must be a non-empty list"):
        load_manifest(p)


def test_panel_empty_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel: []
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"'panel' must be a non-empty list"):
        load_manifest(p)


def test_adversary_not_a_mapping_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            owns_schema_constraint_blocker: true
        adversary: "just a string"
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"'adversary' must be a mapping"):
        load_manifest(p)


def test_addendums_not_a_list_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: "foo"
        """,
    )
    with pytest.raises(ManifestError, match=r"'addendums' must be a list"):
        load_manifest(p)


def test_yaml_parse_error_wrapped_in_manifest_error(tmp_path: Path) -> None:
    p = tmp_path / "personas.yaml"
    p.write_text("panel: [\nbroken")
    with pytest.raises(ManifestError, match=r"failed to parse"):
        load_manifest(p)


def test_unknown_panel_key_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            mov_c: true
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"unknown key\(s\): \['mov_c'\]"):
        load_manifest(p)


@pytest.mark.parametrize("name", ["alpha", "adversary"])
def test_cli_rejects_legacy_file_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    manifest = yaml.safe_load(_MINIMAL_VALID)
    persona = manifest["panel"][0] if name == "alpha" else manifest["adversary"]
    persona["file"] = f"{name}.md"
    path = _write(tmp_path, yaml.safe_dump(manifest))
    assert _main(["--manifest", str(path), "--list", "all-known-files"]) == 3
    assert "unknown key(s): ['file']" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["alpha", "adversary"])
def test_persona_name_rejects_a_trailing_newline(tmp_path: Path, name: str) -> None:
    manifest = _MINIMAL_VALID.replace(f"name: {name}\n", f'name: "{name}\\n"\n')
    with pytest.raises(ManifestError, match="must match"):
        load_manifest(_write(tmp_path, manifest))


def test_unknown_keys_of_different_types_report_a_manifest_error(tmp_path: Path) -> None:
    manifest = _MINIMAL_VALID.replace(
        "    description: alpha", "    file: alpha.md\n    1: extra\n    description: alpha"
    )
    with pytest.raises(ManifestError, match=r"unknown key\(s\): \['file', 1\]"):
        load_manifest(_write(tmp_path, manifest))


def test_unknown_adversary_key_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
          rol: panel
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"adversary has unknown key\(s\): \['rol'\]"):
        load_manifest(p)


def test_panel_owns_schema_constraint_blocker_must_be_bool(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            owns_schema_constraint_blocker: "true"
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(
        ManifestError,
        match=r"'owns_schema_constraint_blocker' must be a boolean, got str",
    ):
        load_manifest(p)


def test_panel_name_must_be_string(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: 123
            description: alpha persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"'name' must be a string, got int"):
        load_manifest(p)


def test_addendum_must_be_string(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums:
          - key: val
        """,
    )
    with pytest.raises(ManifestError, match=r"addendums\[0\] must be a string, got dict"):
        load_manifest(p)


def test_unicode_decode_error_wrapped_in_manifest_error(tmp_path: Path) -> None:
    p = tmp_path / "personas.yaml"
    p.write_bytes(b"panel:\n  - name: \xff\xfe\xfd\n")
    with pytest.raises(ManifestError, match=r"failed to read"):
        load_manifest(p)


def test_addendum_collides_with_panel_file_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums:
          - alpha.md
        """,
    )
    with pytest.raises(ManifestError, match=r"addendums collide.*alpha\.md"):
        load_manifest(p)


def test_addendum_collides_with_adversary_file_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums:
          - adversary.md
        """,
    )
    with pytest.raises(ManifestError, match=r"addendums collide.*adversary\.md"):
        load_manifest(p)


def test_direct_manifest_construction_validates_empty_panel() -> None:
    adv = Persona(name="adversary", description="adversary persona")
    with pytest.raises(ManifestError, match=r"panel must be non-empty"):
        Manifest(panel=(), adversary=adv)


def test_direct_manifest_construction_validates_zero_owners() -> None:
    adv = Persona(name="adversary", description="adversary persona")
    panel = (
        Persona(name="a", description="a persona"),
        Persona(name="b", description="b persona"),
    )
    with pytest.raises(ManifestError, match=r"got 0"):
        Manifest(panel=panel, adversary=adv)


def test_direct_manifest_construction_validates_duplicate_names() -> None:
    adv = Persona(name="adversary", description="adversary persona")
    panel = (
        Persona(name="a", description="a persona", owns_schema_constraint_blocker=True),
        Persona(name="a", description="a duplicate"),
    )
    with pytest.raises(ManifestError, match=r"duplicate panel persona name: a"):
        Manifest(panel=panel, adversary=adv)


def test_persona_file_is_derived() -> None:
    p = Persona(name="alpha", description="alpha persona", move_c=True)
    assert p.file == "alpha.md"


def test_cli_list_panel_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = _write(tmp_path, _MINIMAL_VALID)
    rc = _main(["--manifest", str(p), "--list", "panel-files"])
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["alpha.md"]


def test_cli_list_addendums(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    yaml_body = _MINIMAL_VALID.replace("addendums: []", "addendums: [_extra.md]")
    p = _write(tmp_path, yaml_body)
    rc = _main(["--manifest", str(p), "--list", "addendums"])
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["_extra.md"]


def test_cli_list_schema_constraint_owner(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p = _write(tmp_path, _MINIMAL_VALID)
    rc = _main(["--manifest", str(p), "--list", "schema-constraint-owner"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == "alpha"


def test_cli_exit_code_3_on_manifest_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    nonexistent = tmp_path / "missing.yaml"
    rc = _main(["--manifest", str(nonexistent), "--list", "panel-names"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "manifest error:" in err


def test_cli_exit_code_2_on_invalid_choice(tmp_path: Path) -> None:
    p = _write(tmp_path, _MINIMAL_VALID)
    with pytest.raises(SystemExit) as exc_info:
        _main(["--manifest", str(p), "--list", "bogus"])
    assert exc_info.value.code == 2


def test_panel_description_missing_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(
        ManifestError, match=r"panel\[0\] 'alpha': missing required key 'description'"
    ):
        load_manifest(p)


def test_panel_description_not_string_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: 42
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"panel\[0\] 'alpha': 'description' must be a string"):
        load_manifest(p)


def test_panel_description_empty_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: "   "
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"panel\[0\] 'alpha': 'description' must be non-empty"):
        load_manifest(p)


def test_panel_description_leading_hyphen_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: "- alpha persona"
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(
        ManifestError,
        match=(
            r"panel\[0\] 'alpha': 'description' must not start with '-' "
            r"\(generator prepends the bullet\)"
        ),
    ):
        load_manifest(p)


def test_adversary_description_missing_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
        addendums: []
        """,
    )
    with pytest.raises(
        ManifestError, match=r"adversary 'adversary': missing required key 'description'"
    ):
        load_manifest(p)


def test_adversary_description_not_string_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: [list, not, string]
        addendums: []
        """,
    )
    with pytest.raises(
        ManifestError, match=r"adversary 'adversary': 'description' must be a string"
    ):
        load_manifest(p)


def test_adversary_description_empty_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: ""
        addendums: []
        """,
    )
    with pytest.raises(
        ManifestError, match=r"adversary 'adversary': 'description' must be non-empty"
    ):
        load_manifest(p)


def test_adversary_description_leading_hyphen_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: "- adversary persona"
        addendums: []
        """,
    )
    with pytest.raises(
        ManifestError,
        match=(
            r"adversary 'adversary': 'description' must not start with '-' "
            r"\(generator prepends the bullet\)"
        ),
    ):
        load_manifest(p)


def test_persona_name_with_bracket_rejected(tmp_path: Path) -> None:
    """Names containing ']' would corrupt regen_schema_enum.py's splice regex."""
    p = _write(
        tmp_path,
        """
        panel:
          - name: 'bad]name'
            description: some persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"name.*must match"):
        load_manifest(p)


def test_persona_name_uppercase_rejected(tmp_path: Path) -> None:
    """Names must be lowercase identifiers (no uppercase)."""
    p = _write(
        tmp_path,
        """
        panel:
          - name: BadName
            description: some persona
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"name.*must match"):
        load_manifest(p)


def test_adversary_name_uppercase_rejected(tmp_path: Path) -> None:
    """The name-shape constraint applies to the adversary too."""
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: alpha persona
            owns_schema_constraint_blocker: true
        adversary:
          name: Adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=r"name.*must match"):
        load_manifest(p)


@pytest.mark.parametrize("key", ["move_a", "move_a1", "move_b", "move_c"])
def test_move_flag_must_be_boolean(tmp_path: Path, key: str) -> None:
    p = _write(
        tmp_path,
        f"""
        panel:
          - name: alpha
            description: "alpha persona"
            {key}: "false"
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=rf"'{key}' must be a boolean, got str"):
        load_manifest(p)


def test_move_flags_default_to_false_when_absent(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: "alpha persona"
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: "adversary persona"
        addendums: []
        """,
    )
    alpha = load_manifest(p).panel[0]
    assert (alpha.move_a, alpha.move_a1, alpha.move_b, alpha.move_c) == (
        False,
        False,
        False,
        False,
    )


def test_move_accessors_select_the_flagged_personas(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        """
        panel:
          - name: alpha
            description: "alpha persona"
            move_a: true
            move_b: true
            owns_schema_constraint_blocker: true
          - name: beta
            description: "beta persona"
            move_a1: true
            move_c: true
        adversary:
          name: adversary
          description: "adversary persona"
        addendums: []
        """,
    )
    m = load_manifest(p)
    assert [x.name for x in m.move_a_personas()] == ["alpha"]
    assert [x.name for x in m.move_a1_personas()] == ["beta"]
    assert [x.name for x in m.move_b_personas()] == ["alpha"]
    assert [x.name for x in m.move_c_personas()] == ["beta"]


@pytest.mark.parametrize("key", ["move_a", "move_a1", "move_b"])
def test_unknown_adversary_move_key_rejected(tmp_path: Path, key: str) -> None:
    p = _write(
        tmp_path,
        f"""
        panel:
          - name: alpha
            description: alpha persona
            description: "alpha persona"
            owns_schema_constraint_blocker: true
        adversary:
          name: adversary
          description: adversary persona
          {key}: true
        addendums: []
        """,
    )
    with pytest.raises(ManifestError, match=rf"adversary has unknown key\(s\): \['{key}'\]"):
        load_manifest(p)


@pytest.mark.parametrize("key", ["move_a", "move_a1", "move_b", "move_c"])
def test_direct_manifest_construction_rejects_adversary_move_flag(key: str) -> None:
    bad_adv = Persona(name="adversary", description="adversary persona", **{key: True})
    panel = (Persona(name="a", description="a persona", owns_schema_constraint_blocker=True),)
    with pytest.raises(ManifestError, match=r"adversary 'adversary' must not set"):
        Manifest(panel=panel, adversary=bad_adv)
