"""generated-file replacement preserves permissions and reports write failures."""

from __future__ import annotations

from pathlib import Path

import generator_io
import pytest


@pytest.mark.parametrize("mode", [0o644, 0o755])
def test_atomic_write_preserves_mode(tmp_path: Path, mode: int) -> None:
    target = tmp_path / "target.sh"
    target.write_text("before\n")
    target.chmod(mode)

    generator_io.atomic_write(target, "after\n")

    assert target.read_text() == "after\n"
    assert target.stat().st_mode & 0o7777 == mode


@pytest.mark.parametrize("cleanup_failure", [None, "exists", "unlink"])
def test_failed_replacement_preserves_target_and_original_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_failure: str | None
) -> None:
    target = tmp_path / "target.sh"
    target.write_text("before\n")
    target.chmod(0o755)
    temporary = tmp_path / "target.sh.tmp"
    replacement_error = OSError("replacement failed")

    def fail_replace(source: Path, destination: Path) -> None:
        raise replacement_error

    def fail_cleanup(path: Path) -> None:
        raise OSError("cleanup failed")

    with monkeypatch.context() as failure_patch:
        failure_patch.setattr(generator_io.os, "replace", fail_replace)
        if cleanup_failure is not None:
            failure_patch.setattr(Path, cleanup_failure, fail_cleanup)

        with pytest.raises(OSError) as raised:
            generator_io.atomic_write(target, "after\n")

    assert raised.value is replacement_error
    assert target.read_text() == "before\n"
    assert target.stat().st_mode & 0o7777 == 0o755
    assert temporary.exists() is (cleanup_failure is not None)
