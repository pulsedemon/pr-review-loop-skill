"""shared file output for manifest-driven generators."""

import difflib
import io
import os
import re
import sys
import tempfile
from collections.abc import Callable, Iterable
from contextlib import redirect_stderr
from pathlib import Path
from typing import NoReturn

DRIFT_EXIT = 5
MANIFEST_ERROR_EXIT = 3


def run(main: Callable[[list[str]], int]) -> NoReturn:
    """use UTF-8 for generator CLI help and diagnostics."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    if sys.stderr is None:
        with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stderr(sink):
            raise SystemExit(main(sys.argv[1:]))
    raise SystemExit(main(sys.argv[1:]))


def atomic_write(path: Path, content: str) -> None:
    """preserve target permissions when replacing generated content."""
    stream = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
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


_LINE_ENDING = re.compile(r"\r\n|\r|\n")


def splice_body(match: re.Match[str], body: str) -> str:
    """splice an LF-rendered body into group two, preserving line endings by position."""
    if "\n" in body:
        endings = iter(_LINE_ENDING.findall(match[2]))
        nearby = _LINE_ENDING.search(match[0]) or _LINE_ENDING.search(match.string)
        default = nearby[0] if nearby else "\n"
        body = re.sub(r"\n", lambda _: next(endings, default), body)
    return match.string[: match.start(2)] + body + match.string[match.end(2) :]


def sub_region(region: re.Pattern[str], text: str, body: str, error: str) -> str:
    """replace the middle of the first match of ``region``'s three groups with ``body``.

    exits with ``error`` when the region does not match.
    """
    match = region.search(text)
    if match is None:
        fail(error)
    return splice_body(match, body)


def sync(targets: Iterable[tuple[Path, Callable[[str], str]]], *, check: bool) -> bool:
    """print each drifted target's diff in check mode, write it otherwise.

    returns whether any target differed.
    """
    drifted = False
    for path, regen in targets:
        try:
            current = path.read_bytes().decode("utf-8")
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
