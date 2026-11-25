"""Unit tests for scripts/regen_adversary_caps.py.

Each test seeds an isolated tree under tmp_path and exercises --check
or --write. The fixtures keep the surfaces minimal but structurally
identical to the real ones so the generator's regex anchors are real-
world tested, not toy-tested.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "regen_adversary_caps.py"


def _seed(tmp_path: Path, cap: int = 2) -> dict[str, Path]:
    manifest = tmp_path / "manifests" / "adversary-caps.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(f"cap: {cap}\n")

    schema_path = tmp_path / "templates" / "state.schema.json"
    schema_path.parent.mkdir(parents=True)
    schema_path.write_text(
        json.dumps(
            {
                "properties": {
                    "shallow_adversary_runs": {"type": "integer", "maximum": cap},
                    "shallow_approval_adversary_runs": {"type": "integer", "maximum": cap},
                }
            },
            indent=2,
        )
        + "\n"
    )

    helper_path = tmp_path / "scripts" / "_adversary_caps.sh"
    helper_path.parent.mkdir(parents=True)
    helper_path.write_text(
        "#!/usr/bin/env bash\n"
        "# [[[cog: adversary_caps_sh ]]]\n"
        f'if [[ -n "${{ADVERSARY_CAP:-}}" && "${{ADVERSARY_CAP}}" != "{cap}" ]]; then\n'
        f"  echo \"ERROR: ADVERSARY_CAP is preset to '${{ADVERSARY_CAP}}', "
        f"expected '{cap}'.\" >&2\n"
        '  echo "       Unset it before sourcing scripts/_adversary_caps.sh." >&2\n'
        "  return 1 2>/dev/null || exit 1\n"
        "fi\n"
        f"readonly ADVERSARY_CAP={cap}\n"
        "# [[[end]]]\n"
    )

    doc_path = tmp_path / "docs" / "adversary.md"
    doc_path.parent.mkdir(parents=True)
    doc_path.write_text(
        "# Adversary\n\n"
        "<!-- regen:adversary-caps:start -->\n"
        f"The cap is {cap} (see ADVERSARY_CAP in templates/state.schema.json).\n"
        "<!-- regen:adversary-caps:end -->\n"
    )

    return {
        "manifest": manifest,
        "schema": schema_path,
        "helper": helper_path,
        "doc": doc_path,
    }


def _run(paths: dict[str, Path], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--manifest",
            str(paths["manifest"]),
            "--schema",
            str(paths["schema"]),
            "--helper",
            str(paths["helper"]),
            "--doc",
            str(paths["doc"]),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_clean_tree_exits_zero(tmp_path: Path) -> None:
    paths = _seed(tmp_path, cap=2)
    result = _run(paths, "--check")
    assert result.returncode == 0, result.stderr


def test_check_drifted_schema_exits_five(tmp_path: Path) -> None:
    paths = _seed(tmp_path, cap=2)
    text = paths["schema"].read_text().replace('"maximum": 2', '"maximum": 3', 1)
    paths["schema"].write_text(text)
    result = _run(paths, "--check")
    assert result.returncode == 5
    assert "shallow_adversary_runs" in result.stderr or "maximum" in result.stderr


def test_check_drifted_helper_exits_five(tmp_path: Path) -> None:
    paths = _seed(tmp_path, cap=2)
    paths["helper"].write_text(
        paths["helper"].read_text().replace("ADVERSARY_CAP=2", "ADVERSARY_CAP=3")
    )
    result = _run(paths, "--check")
    assert result.returncode == 5


def test_check_drifted_doc_exits_five(tmp_path: Path) -> None:
    paths = _seed(tmp_path, cap=2)
    paths["doc"].write_text(paths["doc"].read_text().replace("The cap is 2", "The cap is 3"))
    result = _run(paths, "--check")
    assert result.returncode == 5


def test_write_repairs_drift(tmp_path: Path) -> None:
    paths = _seed(tmp_path, cap=2)
    paths["helper"].chmod(0o755)
    paths["helper"].write_text(
        paths["helper"].read_text().replace("ADVERSARY_CAP=2", "ADVERSARY_CAP=99")
    )
    write = _run(paths, "--write")
    assert write.returncode == 0, write.stderr
    assert paths["helper"].stat().st_mode & 0o7777 == 0o755
    assert "ADVERSARY_CAP=2\n" in paths["helper"].read_text()
    check = _run(paths, "--check")
    assert check.returncode == 0, check.stderr


def test_missing_manifest_exits_three(tmp_path: Path) -> None:
    paths = _seed(tmp_path, cap=2)
    paths["manifest"].unlink()
    result = _run(paths, "--check")
    assert result.returncode == 3


def test_missing_target_exits_three_without_traceback(tmp_path: Path) -> None:
    paths = _seed(tmp_path, cap=2)
    paths["doc"].unlink()
    result = _run(paths, "--check")
    assert result.returncode == 3
    assert f"failed to read {paths['doc']}" in result.stderr
    assert "Traceback" not in result.stderr


def test_missing_doc_region_exits_three(tmp_path: Path) -> None:
    paths = _seed(tmp_path, cap=2)
    paths["doc"].write_text("# Adversary\n\nThe cap is 2.\n")
    result = _run(paths, "--write")
    assert result.returncode == 3
    assert "could not find regen:adversary-caps region" in result.stderr


def test_write_propagates_cap_to_preset_guard(tmp_path: Path) -> None:
    paths = _seed(tmp_path, cap=2)
    paths["manifest"].write_text("cap: 5\n")
    write = _run(paths, "--write")
    assert write.returncode == 0, write.stderr
    helper_text = paths["helper"].read_text()
    assert '!= "5"' in helper_text, helper_text
    assert "expected '5'" in helper_text, helper_text
    assert "ADVERSARY_CAP=5" in helper_text, helper_text
    assert '!= "2"' not in helper_text, helper_text
