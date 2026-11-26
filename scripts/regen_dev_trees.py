"""Regenerate the dev-tree skip lists from manifests/dev-trees.yaml.

Surfaces (all four written from one manifest list):
  - install.sh: the CURSOR_INSTALL_SKIP_NAMES bash array.
  - tests/run.sh: the cap-drift grep's --exclude-dir flags.
  - tests/bats/test_helper.bash: copy_skill_tree's rsync --exclude flags.
  - scripts/regen_move_a1_enum.py: the leading _GREP_EXCLUDES entries, ahead
    of that generator's own content-specific excludes.

Each surface needs different syntax for the same names, which is the whole
reason the list drifted by hand. Content-specific excludes stay in their
consumers; only the dev-only trees come from the manifest.

Modes mirror cog: --check exits 0/5, --write rewrites in place atomically.
Manifest and target errors exit 3.

Spec: docs/generators.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import generator_io
import yaml

# A dev-tree entry is a bare filename: no separators, no shell metacharacters,
# no leading dash that grep or rsync would read as a flag. `.` and `..` pass
# this pattern but are rejected separately: `find . -name .` matches the search
# root, pruning the whole tree.
_SAFE_NAME = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._-]*")

_INSTALL_REGION = re.compile(
    r"(# \[\[\[cog: dev_trees_install \]\]\](?:\r\n|\r|\n))(.*?)(# \[\[\[end\]\]\])",
    re.DOTALL,
)
_RUNSH_REGION = re.compile(
    r"(# \[\[\[cog: dev_trees_grep \]\]\](?:\r\n|\r|\n))(.*?)( *# \[\[\[end\]\]\])",
    re.DOTALL,
)
_HELPER_REGION = re.compile(
    r"(# \[\[\[cog: dev_trees_rsync \]\]\](?:\r\n|\r|\n))(.*?)( *# \[\[\[end\]\]\])",
    re.DOTALL,
)
_MOVE_A1_REGION = re.compile(
    r"(    # \[\[\[cog: dev_trees_py \]\]\](?:\r\n|\r|\n))(.*?)(    # \[\[\[end\]\]\])",
    re.DOTALL,
)


# Names that are not always directories. A trailing slash restricts an rsync
# pattern to directories, which would leak `.git` when it is a worktree's
# gitdir pointer file, and would never match `.DS_Store` at all.
_NOT_ALWAYS_A_DIR = frozenset({".git", ".DS_Store"})


def _rsync_pattern(name: str) -> str:
    return name if name in _NOT_ALWAYS_A_DIR else f"{name}/"


def _regen_install(text: str, names: list[str]) -> str:
    body = f"CURSOR_INSTALL_SKIP_NAMES=({' '.join(names)})\n"
    return _sub_region(_INSTALL_REGION, text, body, "install.sh", "dev_trees_install")


def _regen_runsh(text: str, names: list[str]) -> str:
    # Four flags per line keeps the generated block near the width of the
    # hand-written one it replaced.
    lines = []
    for i in range(0, len(names), 4):
        flags = " ".join(f"--exclude-dir={n}" for n in names[i : i + 4])
        lines.append(f"  {flags}\n")
    body = "CAP_GREP_EXCLUDES=(\n" + "".join(lines) + ")\n"
    return _sub_region(_RUNSH_REGION, text, body, "tests/run.sh", "dev_trees_grep")


def _regen_helper(text: str, names: list[str]) -> str:
    entries = "".join(f"    --exclude='{_rsync_pattern(n)}'\n" for n in names)
    body = "  local excludes=(\n" + entries + "  )\n"
    return _sub_region(_HELPER_REGION, text, body, "tests/bats/test_helper.bash", "dev_trees_rsync")


def _regen_move_a1(text: str, names: list[str]) -> str:
    body = "".join(f'    "{n}",\n' for n in names)
    return _sub_region(_MOVE_A1_REGION, text, body, "scripts/regen_move_a1_enum.py", "dev_trees_py")


def _sub_region(region: re.Pattern[str], text: str, body: str, label: str, marker: str) -> str:
    return generator_io.sub_region(
        region,
        text,
        body,
        f"regen_dev_trees: could not find the {marker} cog region in {label}. "
        "Have the file's cog markers been edited?",
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    repo = Path(__file__).resolve().parent.parent
    parser.add_argument("--manifest", type=Path, default=repo / "manifests" / "dev-trees.yaml")
    parser.add_argument("--install", type=Path, default=repo / "install.sh")
    parser.add_argument("--runsh", type=Path, default=repo / "tests" / "run.sh")
    parser.add_argument("--helper", type=Path, default=repo / "tests" / "bats" / "test_helper.bash")
    parser.add_argument("--move-a1", type=Path, default=repo / "scripts" / "regen_move_a1_enum.py")
    args = parser.parse_args(argv)
    if not args.write:
        args.check = True

    try:
        manifest = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
        raw = manifest["dev_trees"]
        # Check the type before list(): a bare string would become its
        # characters and a mapping its keys, either of which can pass every
        # later check and regenerate a skip list that means something else.
        if not isinstance(raw, list):
            raise ValueError(f"dev_trees must be a list, got {type(raw).__name__}")
        names = list(raw)
        if not names or not all(isinstance(n, str) and n for n in names):
            raise ValueError("dev_trees must be a non-empty list of strings")
        # Entries land unquoted in a bash array and a grep flag, so anything
        # that is not a single plain path component would generate shell that
        # splits, globs, or silently matches the wrong thing.
        bad = [n for n in names if not _SAFE_NAME.fullmatch(n) or n in {".", ".."}]
        if bad:
            raise ValueError(
                f"dev_trees entries must be single path components without "
                f"whitespace, quotes, or '/': {bad}"
            )
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate dev_trees entries: {dupes}")
    except (FileNotFoundError, KeyError, TypeError, ValueError, yaml.YAMLError) as e:
        print(f"regen_dev_trees: manifest error: {e}", file=sys.stderr)
        return generator_io.MANIFEST_ERROR_EXIT

    drifted = generator_io.sync(
        [
            (args.install, lambda text: _regen_install(text, names)),
            (args.runsh, lambda text: _regen_runsh(text, names)),
            (args.helper, lambda text: _regen_helper(text, names)),
            (args.move_a1, lambda text: _regen_move_a1(text, names)),
        ],
        check=args.check,
    )

    if args.check and drifted:
        print(
            "\nregen_dev_trees: dev-tree skip lists are out of date. "
            "Run scripts/regen.sh to regenerate.",
            file=sys.stderr,
        )
        return generator_io.DRIFT_EXIT
    return 0


if __name__ == "__main__":
    generator_io.run(main)
