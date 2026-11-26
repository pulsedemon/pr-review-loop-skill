"""tests for the reviewer.enum slice rewriter."""

from __future__ import annotations

import json
from pathlib import Path

import generator_io
import pytest
import regen_schema_enum  # type: ignore[import-not-found]  # sibling module made importable by conftest.py
from personas_fixture import write_personas_yaml  # type: ignore[import-not-found]


def _write_schema(tmp_path: Path, enum_items: list[str]) -> Path:
    """Write a minimal schema with a reviewer.enum block matching the renderer's formatting.

    The renderer (regen_schema_enum._render_enum_body) emits items at 8-space indent
    and places the closing bracket after 6 spaces; replicate that exactly so a
    matching manifest produces a byte-identical schema.
    """
    if enum_items:
        items_lines = ",\n".join(f'        "{name}"' for name in enum_items)
        enum_body = "\n" + items_lines + "\n      "
    else:
        enum_body = ""
    schema_text = (
        "{\n"
        '  "$schema": "http://json-schema.org/draft-07/schema#",\n'
        '  "type": "object",\n'
        '  "properties": {\n'
        '    "reviewer": {\n'
        '      "type": "string",\n'
        f'      "enum": [{enum_body}]\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    p = tmp_path / "output.schema.json"
    p.write_text(schema_text)
    return p


def _run(args: list[str]) -> int:
    return regen_schema_enum.main(args)


def test_check_returns_0_when_schema_matches_manifest(tmp_path: Path) -> None:
    manifest = write_personas_yaml(tmp_path, ["alpha", "beta"])
    schema = _write_schema(tmp_path, ["alpha", "beta", "adversary"])
    rc = _run(["--check", "--manifest", str(manifest), "--schema", str(schema)])
    assert rc == 0


def test_write_rewrites_drifted_schema(tmp_path: Path) -> None:
    manifest = write_personas_yaml(tmp_path, ["alpha", "beta", "gamma"])
    schema = _write_schema(tmp_path, ["alpha"])  # drifted: missing beta, gamma, adversary
    schema.chmod(0o755)
    rc = _run(["--write", "--manifest", str(manifest), "--schema", str(schema)])
    assert rc == 0
    data = json.loads(schema.read_text())
    assert data["properties"]["reviewer"]["enum"] == ["alpha", "beta", "gamma", "adversary"]
    assert schema.stat().st_mode & 0o7777 == 0o755


def test_write_on_matching_schema_is_a_noop(tmp_path: Path) -> None:
    manifest = write_personas_yaml(tmp_path, ["alpha"])
    schema = _write_schema(tmp_path, ["alpha", "adversary"])
    before = schema.read_text()
    before_stat = schema.stat()
    rc = _run(["--write", "--manifest", str(manifest), "--schema", str(schema)])
    assert rc == 0
    assert schema.read_text() == before
    assert schema.stat().st_ino == before_stat.st_ino
    assert schema.stat().st_mtime_ns == before_stat.st_mtime_ns


def test_check_returns_5_with_diff_on_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = write_personas_yaml(tmp_path, ["alpha", "beta"])
    schema = _write_schema(tmp_path, ["alpha"])  # missing beta + adversary
    before = schema.read_bytes()
    rc = _run(["--check", "--manifest", str(manifest), "--schema", str(schema)])
    assert rc == generator_io.DRIFT_EXIT == 5
    captured = capsys.readouterr()
    assert captured.out == ""
    assert schema.read_bytes() == before
    err = captured.err
    assert f"--- {schema}\n" in err
    assert f"+++ {schema} (regenerated)\n" in err
    assert "beta" in err
    assert "adversary" in err
    assert "scripts/regen.sh" in err


def test_returns_3_when_manifest_is_malformed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "personas.yaml"
    manifest.write_text("panel: []\nadversary:\n  name: x\n  file: x.md\n  description: x\n")
    schema = _write_schema(tmp_path, ["alpha"])
    rc = _run(["--check", "--manifest", str(manifest), "--schema", str(schema)])
    assert rc == generator_io.MANIFEST_ERROR_EXIT == 3
    err = capsys.readouterr().err
    assert "manifest error" in err


def test_returns_3_when_schema_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = write_personas_yaml(tmp_path, ["alpha"])
    missing = tmp_path / "nonexistent.json"
    rc = _run(["--check", "--manifest", str(manifest), "--schema", str(missing)])
    assert rc == generator_io.MANIFEST_ERROR_EXIT == 3
    err = capsys.readouterr().err
    assert "failed to read" in err


def test_returns_3_when_schema_is_unreadable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = write_personas_yaml(tmp_path, ["alpha"])
    schema = tmp_path / "output.schema.json"
    schema.write_bytes(b"\xff\xfe\xfd")
    rc = _run(["--check", "--manifest", str(manifest), "--schema", str(schema)])
    assert rc == generator_io.MANIFEST_ERROR_EXIT == 3
    err = capsys.readouterr().err
    assert "failed to read" in err


def test_exits_3_when_schema_is_not_valid_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = write_personas_yaml(tmp_path, ["alpha"])
    schema = tmp_path / "output.schema.json"
    schema.write_text("{ this is not valid json")
    with pytest.raises(SystemExit) as exc_info:
        _run(["--check", "--manifest", str(manifest), "--schema", str(schema)])
    assert exc_info.value.code == generator_io.MANIFEST_ERROR_EXIT
    assert "not valid JSON" in capsys.readouterr().err


def test_exits_3_when_reviewer_enum_path_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = write_personas_yaml(tmp_path, ["alpha"])
    schema = tmp_path / "output.schema.json"
    schema.write_text(json.dumps({"properties": {"other": {}}}, indent=2))
    with pytest.raises(SystemExit) as exc_info:
        _run(["--check", "--manifest", str(manifest), "--schema", str(schema)])
    assert exc_info.value.code == generator_io.MANIFEST_ERROR_EXIT
    assert "properties.reviewer.enum" in capsys.readouterr().err


def test_exits_3_when_slice_regex_cannot_match_despite_valid_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Valid JSON, valid path, but inline single-line enum that the multi-line
    # slice locator cannot match (no whitespace around the colons/braces).
    manifest = write_personas_yaml(tmp_path, ["alpha"])
    schema = tmp_path / "output.schema.json"
    # Use a JSON shape where the regex's whitespace/order expectations are violated.
    # The regex requires "type":"string","enum":[...] in that order; we put enum first.
    schema.write_text('{"properties":{"reviewer":{"enum":["alpha"],"type":"string"}}}')
    with pytest.raises(SystemExit) as exc_info:
        _run(["--check", "--manifest", str(manifest), "--schema", str(schema)])
    assert exc_info.value.code == generator_io.MANIFEST_ERROR_EXIT
    assert "slice locator regex did not match" in capsys.readouterr().err
