"""shared file output for manifest-driven generators."""

import difflib
import os
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NoReturn

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


def fail(message: str) -> NoReturn:
    """end the run on a target the generator cannot read or rewrite."""
    print(message, file=sys.stderr)
    raise SystemExit(MANIFEST_ERROR_EXIT)


def sub_region(region: re.Pattern[str], text: str, body: str, error: str) -> str:
    """replace the middle of the first match of ``region``'s three groups with ``body``.

    exits with ``error`` when the region does not match.
    """
    new, n = region.subn(lambda m: m.group(1) + body + m.group(3), text, count=1)
    if n != 1:
        fail(error)
    return new


def sync(targets: Iterable[tuple[Path, Callable[[str], str]]], *, check: bool) -> bool:
    """print each drifted target's diff in check mode, write it otherwise.

    returns whether any target differed.
    """
    drifted = False
    for path, regen in targets:
        try:
            current = path.read_text()
        except (OSError, UnicodeDecodeError) as e:
            fail(f"failed to read {path}: {e}")
        regenerated = regen(current)
        if current == regenerated:
            continue
        drifted = True
        if check:
            emit_drift_diff(path, current, regenerated)
        else:
            atomic_write(path, regenerated)
    return drifted
