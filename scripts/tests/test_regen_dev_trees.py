"""Unit tests for scripts/regen_dev_trees.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GENERATOR = REPO_ROOT / "scripts" / "regen_dev_trees.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from regen_dev_trees import _rsync_pattern  # noqa: E402


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # A trailing slash restricts an rsync pattern to directories. `.git` is
        # a file in a git worktree (the gitdir pointer) and `.DS_Store` is
        # always a file, so both must stay bare or they stop matching.
        (".git", ".git"),
        (".DS_Store", ".DS_Store"),
        (".venv", ".venv/"),
        ("__pycache__", "__pycache__/"),
        ("worktrees", "worktrees/"),
    ],
)
def test_rsync_pattern_slashes_only_directories(name: str, expected: str) -> None:
    assert _rsync_pattern(name) == expected


def test_check_passes_on_the_checked_in_tree() -> None:
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr


def test_manifest_without_dev_trees_key_exits_3(tmp_path: Path) -> None:
    manifest = tmp_path / "dev-trees.yaml"
    manifest.write_text("other_key: [a]\n")
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check", "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 3
    assert "manifest error" in proc.stderr


@pytest.mark.parametrize(
    "entry",
    [
        "a b",  # splits into two bash array entries
        "docs/superpowers",  # a path, not a dev tree; belongs in the consumer
        "-rf",  # grep and rsync would read it as a flag
        '.git"; rm -rf /',  # quote break-out
        ".",  # `find . -name .` matches the root and prunes everything
        "..",
    ],
)
def test_unsafe_manifest_entry_exits_3(tmp_path: Path, entry: str) -> None:
    manifest = tmp_path / "dev-trees.yaml"
    manifest.write_text(yaml.safe_dump({"dev_trees": [entry]}))
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check", "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 3
    assert "single path components" in proc.stderr


@pytest.mark.parametrize(
    ("body", "label"),
    [
        ("dev_trees: .git\n", "a bare string becomes its characters"),
        ("dev_trees:\n  .git: yes\n", "a mapping becomes its keys"),
        ("dev_trees: 5\n", "a scalar is not iterable as names"),
        ("dev_trees:\n", "null"),
    ],
)
def test_non_list_manifest_value_exits_3(tmp_path: Path, body: str, label: str) -> None:
    # `dev_trees: .git` would otherwise regenerate `(. g i t)`, and `.` as a
    # find -name pattern matches every directory.
    manifest = tmp_path / "dev-trees.yaml"
    manifest.write_text(body)
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check", "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 3, label
    assert "manifest error" in proc.stderr


def test_duplicate_manifest_entries_exit_3(tmp_path: Path) -> None:
    manifest = tmp_path / "dev-trees.yaml"
    manifest.write_text("dev_trees:\n  - .git\n  - .git\n")
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check", "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 3
    assert "duplicate" in proc.stderr


def test_write_preserves_the_target_file_mode(tmp_path: Path) -> None:
    manifest = tmp_path / "dev-trees.yaml"
    manifest.write_text("dev_trees:\n  - .git\n  - .venv\n")
    targets = [
        (
            "--install",
            "install.sh",
            "dev_trees_install",
            "",
            0o755,
            "CURSOR_INSTALL_SKIP_NAMES=(.git .venv)\n",
        ),
        (
            "--runsh",
            "run.sh",
            "dev_trees_grep",
            "",
            0o755,
            "CAP_GREP_EXCLUDES=(\n  --exclude-dir=.git --exclude-dir=.venv\n)\n",
        ),
        (
            "--helper",
            "test_helper.bash",
            "dev_trees_rsync",
            "",
            0o644,
            "  local excludes=(\n    --exclude='.git'\n    --exclude='.venv/'\n  )\n",
        ),
        (
            "--move-a1",
            "regen_move_a1_enum.py",
            "dev_trees_py",
            "    ",
            0o644,
            '    ".git",\n    ".venv",\n',
        ),
    ]
    args = [sys.executable, str(GENERATOR), "--write", "--manifest", str(manifest)]
    expected = []
    for option, filename, marker, indent, mode, body in targets:
        path = tmp_path / filename
        start = f"{indent}# [[[cog: {marker} ]]]\n"
        end = f"{indent}# [[[end]]]\n"
        path.write_text(start + "stale\n" + end)
        path.chmod(mode)
        args.extend([option, str(path)])
        expected.append((path, start + body + end, mode))

    proc = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True)

    assert proc.returncode == 0, proc.stderr
    for path, content, mode in expected:
        assert path.read_text() == content
        assert path.stat().st_mode & 0o7777 == mode


def test_write_fails_when_a_cog_region_is_missing(tmp_path: Path) -> None:
    install = tmp_path / "install.sh"
    install.write_text(
        "# [[[cog: dev_trees_install ]]]\nCURSOR_INSTALL_SKIP_NAMES=(stale)\n# [[[end]]]\n"
    )
    manifest = tmp_path / "dev-trees.yaml"
    manifest.write_text("dev_trees:\n  - .git\n  - .venv\n")

    args = [
        sys.executable,
        str(GENERATOR),
        "--manifest",
        str(manifest),
        "--install",
        str(install),
        "--runsh",
        str(install),
        "--helper",
        str(install),
        "--move-a1",
        str(install),
    ]
    # Only the install region exists in this fixture, so the other three
    # emitters must fail loudly rather than silently writing nothing.
    proc = subprocess.run([*args, "--write"], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "cog region" in proc.stderr
