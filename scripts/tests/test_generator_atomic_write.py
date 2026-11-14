"""Every generator's _atomic_write must preserve the target's file mode.

os.replace installs the temp file's default mode, so a regen would silently
drop an executable target to 644. install.sh, tests/run.sh, and
scripts/_adversary_caps.sh are all 755 on disk, and ./install.sh is the
documented entry point.

One parametrized test rather than a copy per generator, so a generator added
later is covered by adding a name to the list.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

GENERATORS = [
    "regen_adversary_caps",
    "regen_dev_trees",
    "regen_move_a1_enum",
    "regen_panel_counts",
    "regen_schema_enum",
]


def test_every_generator_module_is_listed() -> None:
    # A new regen_*.py that skips this list would ship the bug again.
    on_disk = {p.stem for p in (REPO_ROOT / "scripts").glob("regen_*.py")}
    assert on_disk == set(GENERATORS), f"unlisted generators: {on_disk ^ set(GENERATORS)}"


@pytest.mark.parametrize("module_name", GENERATORS)
@pytest.mark.parametrize("mode", [0o644, 0o755])
def test_atomic_write_preserves_mode(tmp_path: Path, module_name: str, mode: int) -> None:
    module = importlib.import_module(module_name)
    target = tmp_path / "target.sh"
    target.write_text("before\n")
    target.chmod(mode)

    module._atomic_write(target, "after\n")

    assert target.read_text() == "after\n"
    assert target.stat().st_mode & 0o777 == mode
