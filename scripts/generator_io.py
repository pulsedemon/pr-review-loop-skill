"""shared file output for manifest-driven generators."""

import difflib
import io
import os
import re
import sys
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NoReturn

DRIFT_EXIT = 5
MANIFEST_ERROR_EXIT = 3


def run(main: Callable[[list[str]], int]) -> NoReturn:
    """emit repository text in UTF-8 when a generator runs as a command."""
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    raise SystemExit(main(sys.argv[1:]))


def atomic_write(path: Path, content: str | bytes) -> None:
    """preserve target permissions when replacing generated content."""
    binary = isinstance(content, bytes)
    stream = tempfile.NamedTemporaryFile(
        mode="wb" if binary else "w",
        encoding=None if binary else "utf-8",
        dir=path.parent,
        prefix=".regen-",
        suffix=".tmp",
        delete=False,
    )
    tmp = Path(stream.name)
    try:
        with stream:
            stream.write(content)
        os.chmod(tmp, path.stat().st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            # keep cleanup errors from hiding the write failure.
            pass
        raise


def emit_drift_diff(path: Path, current: str, regenerated: str) -> None:
    diff = difflib.unified_diff(
        io.StringIO(current, newline="").readlines(),
        io.StringIO(regenerated, newline="").readlines(),
        fromfile=str(path),
        tofile=f"{path} (regenerated)",
    )
    for line in diff:
        if line.endswith(("\r", "\n")):
            print(line.removesuffix("\n").removesuffix("\r"), file=sys.stderr)
        else:
            print(line, r"\ No newline at end of file", sep="\n", file=sys.stderr)


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
            current = path.read_text(encoding="utf-8")
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
