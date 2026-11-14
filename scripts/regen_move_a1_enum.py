"""Regenerate the Move A.1 sub-mechanic enum across five mirrors.

Source of truth is ``manifests/move-a1-enum.yaml``. Mirrors:
  - ``templates/state.schema.json``  (inline-array enum at
    ``properties.history.items.properties.move_a1_pattern.enum``)
  - ``reviewers/output.schema.json``  (multi-line enum at
    ``properties.findings.items.properties.move_a1_pattern.enum``)
  - ``SKILL.md``  (sentence inside ``regen:move-a1-enum`` HTML-comment region)
  - ``reviewers/tests.md``  (sentence inside ``regen:move-a1-enum`` region)
  - ``reviewers/adversary.md``  (sentence inside ``regen:move-a1-enum`` region)

``--check`` accumulates drift across all surfaces and exits 5 if any are
dirty (so a single run shows the full picture). ``--write`` rewrites in
place atomically. Manifest errors exit 3.

Future-mirror discovery: ``--check`` scans the tree under
``--out-of-region-root`` (default repo root) for any enum value occurring
outside a known region. Excludes the manifest itself, ``.git/``, ``.worktrees/``,
``worktrees/``, ``tests/bats/``, ``docs/superpowers/``,
``tools/recall-harness/``, and the five mirror files (occurrences inside those
are policed inline by the per-surface checks).

Spec: docs/generators.md
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path

import yaml

_DRIFT_EXIT = 5
_MANIFEST_ERROR_EXIT = 3

_REGION = re.compile(
    r"(<!-- regen:move-a1-enum:start -->)(.*?)(<!-- regen:move-a1-enum:end -->)",
    re.DOTALL,
)

# In-region value list: a comma-separated list of >=2 backticked snake_case
# tokens. After region tightening, this is unambiguous in every mirror —
# each region body contains exactly one such list. Used by _regen_prose
# uniformly across SKILL.md, reviewers/tests.md, reviewers/adversary.md.
_VALUE_LIST = re.compile(r"`[a-z_]+`(?:,\s*`[a-z_]+`)+")

# Numbered Markdown bullet definition with a bold snake_case label, at
# line start. Used to detect stale bullet definitions in reviewers/tests.md
# after a manifest-value rename: any such label outside the regen region
# must be in the current manifest. (Scoped to tests.md only because that
# is the only mirror file that uses the bullet-definition convention; in
# SKILL.md / reviewers/adversary.md the **bold-snake_case** pattern is
# used for unrelated parameter names and would produce false positives.)
_TESTS_BULLET_LABEL = re.compile(r"^\d+\.\s+\*\*([a-z_]+)\*\*", re.MULTILINE)

# Slice-locator regexes for the two schemas. Each anchors on the
# property key + array opener; we rewrite only the enum-array body.
_STATE_ENUM_SLICE = re.compile(
    r'("move_a1_pattern"\s*:\s*\{[^}]*?"enum"\s*:\s*\[)([^\]]*)(\])',
    re.DOTALL,
)
_OUT_ENUM_SLICE = re.compile(
    r'("move_a1_pattern"\s*:\s*\{\s*"type"\s*:\s*"string"\s*,\s*"enum"\s*:\s*\[)'
    r"([^\]]*)"
    r"(\])",
    re.DOTALL,
)


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    # os.replace installs the temp file's default mode, which would strip the
    # executable bit off any target that is run directly.
    os.chmod(tmp, path.stat().st_mode & 0o7777)
    os.replace(tmp, path)


def _render_value_list(values: list[str]) -> str:
    return ", ".join(f"`{v}`" for v in values)


def _render_state_enum_body(values: list[str]) -> str:
    # Inline array: ["a", "b", ...]
    return ", ".join(json.dumps(v) for v in values)


def _render_out_enum_body(values: list[str], indent: int = 14) -> str:
    pad = " " * indent
    inner = ",\n".join(f"{pad}{json.dumps(v)}" for v in values)
    closing_pad = " " * (indent - 2)
    return "\n" + inner + "\n" + closing_pad


def _regen_state_schema(text: str, values: list[str]) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise SystemExit(f"regen_move_a1_enum: state.schema.json is not valid JSON: {e}") from e
    # Walk to confirm move_a1_pattern.enum exists somewhere; we don't pin
    # the path exactly because the schema layout has nested items/properties
    # branches and a structural sanity check is enough.
    if "move_a1_pattern" not in text:
        raise SystemExit("regen_move_a1_enum: move_a1_pattern key not found in state.schema.json")
    body = _render_state_enum_body(values)
    new, n = _STATE_ENUM_SLICE.subn(lambda m: m.group(1) + body + m.group(3), text, count=1)
    if n != 1:
        raise SystemExit(
            "regen_move_a1_enum: could not locate move_a1_pattern.enum slice in "
            "state.schema.json. The schema's formatting around the enum may have "
            "changed."
        )
    # Re-parse to confirm we produced valid JSON.
    try:
        json.loads(new)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"regen_move_a1_enum: regenerated state.schema.json is not valid JSON: {e}"
        ) from e
    _ = data  # parsed only as pre-flight
    return new


def _regen_out_schema(text: str, values: list[str]) -> str:
    try:
        json.loads(text)
    except json.JSONDecodeError as e:
        raise SystemExit(f"regen_move_a1_enum: output.schema.json is not valid JSON: {e}") from e
    if "move_a1_pattern" not in text:
        raise SystemExit("regen_move_a1_enum: move_a1_pattern key not found in output.schema.json")
    # Detect indentation from the existing match so we render with the
    # same per-line pad. Falls back to 14 spaces (the real schema's
    # current indent) if detection fails.
    match = _OUT_ENUM_SLICE.search(text)
    if match is None:
        raise SystemExit(
            "regen_move_a1_enum: could not locate move_a1_pattern.enum slice in output.schema.json."
        )
    inner = match.group(2)
    indent = 14
    indent_match = re.search(r"\n( +)\"", inner)
    if indent_match is not None:
        indent = len(indent_match.group(1))
    body = _render_out_enum_body(values, indent=indent)
    new = text[: match.start(2)] + body + text[match.end(2) :]
    try:
        json.loads(new)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"regen_move_a1_enum: regenerated output.schema.json is not valid JSON: {e}"
        ) from e
    return new


def _regen_prose(text: str, path: Path, values: list[str], *, optional: bool = False) -> str:
    """Rewrite the backticked value list inside regen:move-a1-enum regions.

    Each region body must contain exactly one comma-separated list of
    backticked snake_case tokens (the value list); that list is replaced
    with the manifest-rendered list. Surrounding text inside the region
    is preserved. After region tightening (commit fix), every mirror
    region is narrow enough that exactly one such list is present per
    region, so there is no ambiguity to resolve.
    """
    rendered_list = _render_value_list(values)
    regions = list(_REGION.finditer(text))
    if not regions and optional:
        # SKILL.md's region lives inside the generated §4b Move A.1 bullet,
        # which cog omits when no persona carries the move, so absent is a
        # legitimate state here but never in the hand-written mirrors. A
        # region deleted while a carrier still exists is not missed: cog
        # re-emits the bullet and regen-check fails on the diff.
        return text
    if not regions:
        raise SystemExit(
            f"regen_move_a1_enum: {path}: no regen:move-a1-enum region found. "
            "Wrap the sentence naming the five sub-mechanics with "
            "<!-- regen:move-a1-enum:start --> ... <!-- regen:move-a1-enum:end -->."
        )
    new = text
    rewrote_any = False
    # Iterate regions from end to start so earlier offsets stay valid as
    # we rewrite.
    for region in reversed(regions):
        body = region.group(2)
        body_start = region.start(2)
        body_end = region.end(2)
        sub, n = _VALUE_LIST.subn(rendered_list, body, count=1)
        if n == 0:
            continue
        rewrote_any = True
        new = new[:body_start] + sub + new[body_end:]

    if not rewrote_any:
        raise SystemExit(
            f"regen_move_a1_enum: {path}: no backticked value list found in any "
            "regen:move-a1-enum region. The region must contain a list like "
            "`a`, `b`, `c`, ..."
        )
    return new


# Trees the future-mirror grep MUST skip even if they sit under the search
# root. Paths are relative to the search root; matched as path components.
# Test fixtures (scripts/tests/, tests/bats/) legitimately mention enum
# values to exercise the generator. The generator itself
# (scripts/regen_move_a1_enum.py) carries the values in its docstring
# / sample comments.
_GREP_EXCLUDES = (
    # Dev-only trees, generated from manifests/dev-trees.yaml.
    # [[[cog: dev_trees_py ]]]
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    ".worktrees",
    "worktrees",
    "__pycache__",
    ".DS_Store",
    ".claude",
    ".superpowers",
    # [[[end]]]
    # Content this scan specifically must not read: fixtures that quote enum
    # values on purpose, and the generator's own docstring.
    "scripts/tests",
    "scripts/regen_move_a1_enum.py",
    "tests/bats",
    "docs/superpowers",
    "tools/recall-harness",
)


def _is_excluded(rel: Path) -> bool:
    parts = rel.parts
    for ex in _GREP_EXCLUDES:
        ex_parts = tuple(ex.split("/"))
        # Single-component excludes (e.g. "__pycache__") match at any
        # depth; multi-component excludes (e.g. "scripts/tests") match
        # only as a path prefix.
        if len(ex_parts) == 1:
            if ex_parts[0] in parts:
                return True
        elif len(parts) >= len(ex_parts) and parts[: len(ex_parts)] == ex_parts:
            return True
    return False


def _scan_out_of_region(
    root: Path,
    values: list[str],
    manifest: Path,
    mirror_paths: list[Path],
) -> list[str]:
    """Return a list of "<file>:<lineno>: <line>" hits for any enum value
    occurring outside a known region in any non-excluded file under root."""
    mirror_set = {p.resolve() for p in mirror_paths}
    manifest_resolved = manifest.resolve()
    hits: list[str] = []
    if not root.exists():
        return hits
    for dirpath, dirnames, filenames in os.walk(root):
        current_dir = Path(dirpath)
        rel_dir = current_dir.relative_to(root)
        dirnames[:] = sorted(d for d in dirnames if not _is_excluded(rel_dir / d))
        for filename in sorted(filenames):
            path = current_dir / filename
            rel = path.relative_to(root)
            if _is_excluded(rel):
                continue
            resolved = path.resolve()
            if resolved == manifest_resolved:
                continue
            if resolved in mirror_set:
                continue
            try:
                text = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                for v in values:
                    if re.search(r"\b" + re.escape(v) + r"\b", line):
                        hits.append(f"{path}:{lineno}: {line.strip()}")
                        break
    return hits


def _scan_tests_md_bullet_drift(path: Path, values: list[str]) -> list[str]:
    """Catch stale bullet definitions in reviewers/tests.md after a
    manifest-value rename.

    The Move A.1 procedure block in reviewers/tests.md defines each
    sub-mechanic as a numbered Markdown bullet with a bold snake_case
    label::

        1. **cross_fixture** — A DOM-style assertion ...

    These bullets sit OUTSIDE the named regen:move-a1-enum region (which
    wraps only the trailing "to one of ..." sentence) so that any stale
    label after a manifest rename is detectable as out-of-region prose.

    This scan finds every ``^\\d+\\. **<ident>**`` outside the region
    and requires ``<ident>`` to be a current manifest value. Any label
    not in ``values`` is reported as drift.

    Scoped to ``reviewers/tests.md`` only because that is the lone mirror
    using the bullet-definition convention; in SKILL.md and
    reviewers/adversary.md the same ``**snake_case**`` syntax is used
    for unrelated parameter names and would produce false positives.
    """
    text = path.read_text()
    region_spans = [(m.start(), m.end()) for m in _REGION.finditer(text)]
    value_set = set(values)
    hits: list[str] = []
    for m in _TESTS_BULLET_LABEL.finditer(text):
        if any(s <= m.start() < e for s, e in region_spans):
            continue
        ident = m.group(1)
        if ident not in value_set:
            lineno = text.count("\n", 0, m.start()) + 1
            hits.append(f"{path}:{lineno}: stale bullet label `**{ident}**` not in manifest")
    return hits


def _diff(label: str, before: str, after: str) -> list[str]:
    return list(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=label,
            tofile=f"{label} (regenerated)",
        )
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="diff vs disk (default)")
    mode.add_argument("--write", action="store_true", help="rewrite files in place")
    repo = Path(__file__).resolve().parent.parent
    parser.add_argument("--manifest", type=Path, default=repo / "manifests" / "move-a1-enum.yaml")
    parser.add_argument(
        "--state-schema", type=Path, default=repo / "templates" / "state.schema.json"
    )
    parser.add_argument(
        "--out-schema", type=Path, default=repo / "reviewers" / "output.schema.json"
    )
    parser.add_argument("--skill", type=Path, default=repo / "SKILL.md")
    parser.add_argument("--tests-md", type=Path, default=repo / "reviewers" / "tests.md")
    parser.add_argument("--adv-md", type=Path, default=repo / "reviewers" / "adversary.md")
    parser.add_argument(
        "--out-of-region-root",
        type=Path,
        default=repo,
        help="root for the future-mirror grep (default: repo root)",
    )
    args = parser.parse_args(argv)
    if not args.write:
        args.check = True

    try:
        manifest_data = yaml.safe_load(args.manifest.read_text())
        values = list(manifest_data["move_a1_pattern"])
        if not values or not all(isinstance(v, str) and v for v in values):
            raise ValueError("move_a1_pattern must be a non-empty list of strings")
    except (FileNotFoundError, KeyError, TypeError, ValueError, yaml.YAMLError) as e:
        print(f"regen_move_a1_enum: manifest error: {e}", file=sys.stderr)
        return _MANIFEST_ERROR_EXIT

    mirror_paths = [
        args.state_schema,
        args.out_schema,
        args.skill,
        args.tests_md,
        args.adv_md,
    ]

    targets: list[tuple[str, Path, callable]] = [
        ("state-schema", args.state_schema, _regen_state_schema),
        ("out-schema", args.out_schema, _regen_out_schema),
        ("skill", args.skill, lambda t, v: _regen_prose(t, args.skill, v, optional=True)),
        ("tests-md", args.tests_md, lambda t, v: _regen_prose(t, args.tests_md, v)),
        ("adv-md", args.adv_md, lambda t, v: _regen_prose(t, args.adv_md, v)),
    ]

    drifted = False
    for _label, path, regen in targets:
        before = path.read_text()
        after = regen(before, values)
        if before == after:
            continue
        if args.check:
            sys.stderr.writelines(_diff(str(path), before, after))
            drifted = True
        else:
            _atomic_write(path, after)

    if args.check:
        # Bullet-label drift in reviewers/tests.md: any "1. **<ident>**"
        # bullet outside the named region must have <ident> in the
        # current manifest. Catches stale bullets after a value rename.
        bullet_hits = _scan_tests_md_bullet_drift(args.tests_md, values)
        if bullet_hits:
            sys.stderr.write(
                f"regen_move_a1_enum: {args.tests_md}: stale bullet label(s) — "
                "rename in manifests/move-a1-enum.yaml leaked past tests.md:\n"
            )
            for h in bullet_hits:
                sys.stderr.write(f"  {h}\n")
            drifted = True

        # Future-mirror grep across the rest of the tree.
        out_hits = _scan_out_of_region(args.out_of_region_root, values, args.manifest, mirror_paths)
        if out_hits:
            sys.stderr.write("regen_move_a1_enum: enum value(s) found outside known mirrors:\n")
            for h in out_hits:
                sys.stderr.write(f"  {h}\n")
            drifted = True

        if drifted:
            print(
                "\nregen_move_a1_enum: Move A.1 enum mirrors are out of date or "
                "have stray occurrences. Run scripts/regen.sh to regenerate.",
                file=sys.stderr,
            )
            return _DRIFT_EXIT
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
