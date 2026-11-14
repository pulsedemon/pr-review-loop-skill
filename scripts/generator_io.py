"""shared file output for manifest-driven generators."""

import difflib
import os
import sys
from pathlib import Path


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
