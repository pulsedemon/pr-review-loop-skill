"""shared file output for manifest-driven generators."""

import difflib
import os
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

DRIFT_EXIT = 5
MANIFEST_ERROR_EXIT = 3


def atomic_write(path: Path, content: str) -> None:
    """preserve target permissions when replacing generated content."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content)
        os.chmod(tmp, path.stat().st_mode & 0o7777)
        os.replace(tmp, path)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            # keep cleanup errors from hiding the write failure.
            pass
        raise


def emit_drift_diff(path: Path, current: str, regenerated: str) -> None:
    diff = difflib.unified_diff(
        current.splitlines(keepends=True),
        regenerated.splitlines(keepends=True),
        fromfile=str(path),
        tofile=f"{path} (regenerated)",
    )
    sys.stderr.writelines(diff)


def sub_region(region: re.Pattern[str], text: str, body: str, error: str) -> str:
    """replace the middle of ``region``'s three groups with ``body``.

    exits with ``error`` unless the region matches exactly once.
    """
    new, n = region.subn(lambda m: m.group(1) + body + m.group(3), text, count=1)
    if n != 1:
        raise SystemExit(error)
    return new


def sync(targets: Iterable[tuple[Path, Callable[[str], str]]], *, check: bool) -> bool:
    """print each drifted target's diff in check mode, write it otherwise.

    returns whether any target differed.
    """
    drifted = False
    for path, regen in targets:
        current = path.read_text()
        regenerated = regen(current)
        if current == regenerated:
            continue
        drifted = True
        if check:
            emit_drift_diff(path, current, regenerated)
        else:
            atomic_write(path, regenerated)
    return drifted
