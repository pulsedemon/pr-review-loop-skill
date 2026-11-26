"""generated-file replacement preserves permissions and reports write failures."""

from __future__ import annotations

import os
from pathlib import Path

import generator_io
import pytest


@pytest.mark.parametrize("mode", [0o644, 0o755])
def test_atomic_write_preserves_mode(tmp_path: Path, mode: int) -> None:
    target = tmp_path / "target.sh"
    target.write_text("before\n")
    target.chmod(mode)
    other = tmp_path / "target.sh.tmp"
    other.write_text("reserved")

    generator_io.atomic_write(target, "after\n")

    assert target.read_text() == "after\n"
    assert other.read_text() == "reserved"
    assert target.stat().st_mode & 0o7777 == mode


def test_atomic_write_replaces_a_target_with_a_long_basename(tmp_path: Path) -> None:
    target = tmp_path / ("x" * os.pathconf(tmp_path, "PC_NAME_MAX"))
    target.write_bytes(b"old")
    generator_io.atomic_write(target, "new")
    assert target.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [target]


def test_overlapping_writes_install_each_complete_payload(tmp_path, monkeypatch) -> None:
    target = tmp_path / "target.md"
    target.write_text("original")
    replace = generator_io.os.replace
    sources = []

    def interleave(source, destination):
        sources.append(source)
        if len(sources) == 1:
            generator_io.atomic_write(target, "second")
            assert target.read_text() == "second"
        replace(source, destination)

    monkeypatch.setattr(generator_io.os, "replace", interleave)
    generator_io.atomic_write(target, "first")
    assert len(set(sources)) == 2
    assert target.read_text() == "first"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("cleanup_failure", [False, True])
@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_failed_replacement_preserves_target_and_original_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_failure: bool,
    error_type: type[BaseException],
) -> None:
    target = tmp_path / "target.sh"
    target.write_text("before\n")
    target.chmod(0o755)
    replacement_error = error_type("replacement failed")

    def fail_replace(source: Path, destination: Path) -> None:
        raise replacement_error

    def fail_cleanup(path: Path) -> None:
        raise OSError("cleanup failed")

    with monkeypatch.context() as failure_patch:
        failure_patch.setattr(generator_io.os, "replace", fail_replace)
        if cleanup_failure:
            failure_patch.setattr(Path, "unlink", fail_cleanup)

        with pytest.raises(error_type) as raised:
            generator_io.atomic_write(target, "after\n")

    assert raised.value is replacement_error
    assert target.read_text() == "before\n"
    assert target.stat().st_mode & 0o7777 == 0o755
    assert len(list(tmp_path.glob("*.tmp"))) == int(cleanup_failure)
