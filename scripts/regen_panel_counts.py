"""Regenerate panel-count phrases across the corpus from reviewers/personas.yaml.

Source of truth: ``len(reviewers/personas.yaml#panel)``. Whenever a persona
is added or removed, every running-prose phrase that names the panel size
("the panel of N reviewer personas", "N personas total (panel + adversary)",
…) drifts. This generator promotes every panel-count phrase into a
regen-managed region whose body is rebuilt from the manifest, and runs a
corpus-wide closure scan that forces any new numbered panel-count phrase
to either be wrapped in a region or match a maintained allowlist.

## Region shape (Option A from the design)

Authors wrap each panel-count phrase in named-region markers and supply the
*template* on the line immediately after the start marker, in a hidden
``<!-- template: ... -->`` HTML comment. The line after the template holds
the rendered prose. Region boundaries occupy whole physical lines. Template
text and rendered bodies cannot contain another control comment. The end
marker closes the region:

```
<!-- regen:panel-count-total:start -->
<!-- template: the panel of {n} {personas|persona} -->
the panel of 11 personas
<!-- regen:panel-count-total:end -->
```

Two region kinds:

- ``regen:panel-count-total``: body uses ``n = len(panel)``.
- ``regen:panel-count-total-plus-1``: body uses ``n + 1`` (panel + adversary).

## Placeholders

- ``{n}``: substituted with the integer count (no formatting).
- ``{personas|persona}``: selects ``personas`` for ``n != 1``, ``persona``
  for ``n == 1``. ``n == 0`` renders ``0 personas`` (zero-plural).

Templates may contain Markdown formatting around the placeholders (e.g.
backticks: ``the panel of `{n}` {personas|persona}``). The generator only
substitutes; it doesn't strip formatting.

## Why Option A

Two alternatives were considered:

* **B (template lives on disk as the rendered shape):** authors edit
  ``{n}`` placeholders directly and readers see literal ``{n}`` in
  rendered prose. Bad UX.
* **C (stateless re-render):** the generator reads the rendered body and
  re-derives the template by replacing ``\\d+`` with ``{n}``. Ambiguous:
  ``the other 5 personas`` and ``5 minutes`` look the same to a regex.

Option A keeps the template inline (visible to maintainers but invisible
to Markdown renderers via the HTML comment) and the rendered prose
adjacent. Round-trip is byte-stable.

## Modes

- ``--check`` (default): exit 0 if every region matches its rendered
  template; exit 5 with a unified diff if any region drifted.
- ``--write``: rewrite drifted regions in place (atomic via .tmp +
  ``os.replace``).
- ``--validate-markers``: walk every corpus file and confirm region
  start/end markers are balanced and well-formed; exit 5 with the
  offending file path on imbalance. Run independently of drift detection.
- ``--validate-coverage``: walk every corpus file and require every
  numbered persona-count phrase to either fall inside a regen region or
  match a maintained allowlist pattern. Exit 5 after reporting every
  unhandled phrase.

Exit codes: 0 ok, 3 manifest error or a corpus file ``--check`` or
``--write`` cannot read, 5 drift detected. The validate modes exit 5 on any
failure, an unreadable corpus file included.

## Corpus

``SKILL.md``, ``tests/scenarios/*.md``, ``reviewers/*.md``. Other files
(``docs/``, ``tools/recall-harness/``, ``docs/superpowers/``) are skipped
because the generator globs exact paths without recursion.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import generator_io
from personas_manifest import ManifestError, load_manifest

_KIND_TOTAL = "total"

_CONTROL_RE = re.compile(r"<!-- regen:panel-count-(total|total-plus-1):(start|end) -->")
_TEMPLATE_RE = re.compile(r"<!-- template: (.+?) -->")

_PLACEHOLDER_PERSONAS = "{personas|persona}"
_PLACEHOLDER_N = "{n}"


@dataclass(frozen=True)
class _Region:
    start_line: int  # 0-based index of the start marker
    end_line: int  # 0-based index of the end marker
    kind: str  # "total" or "total-plus-1"
    template: str  # body of the <!-- template: ... --> line


def _render_template(template: str, n: int) -> str:
    """Substitute ``{n}`` and ``{personas|persona}`` placeholders.

    ``{personas|persona}`` selects ``personas`` for ``n != 1`` (including
    ``n == 0``), ``persona`` for ``n == 1``.
    """
    word = "persona" if n == 1 else "personas"
    return template.replace(_PLACEHOLDER_PERSONAS, word).replace(_PLACEHOLDER_N, str(n))


def _corpus_files(root: Path) -> list[Path]:
    """Return the sorted corpus files: SKILL.md, tests/scenarios/*.md, reviewers/*.md."""
    files: list[Path] = []
    skill = root / "SKILL.md"
    if skill.is_file():
        files.append(skill)
    scenarios_dir = root / "tests" / "scenarios"
    if scenarios_dir.is_dir():
        files.extend(sorted(p for p in scenarios_dir.glob("*.md") if p.is_file()))
    reviewers_dir = root / "reviewers"
    if reviewers_dir.is_dir():
        files.extend(sorted(p for p in reviewers_dir.glob("*.md") if p.is_file()))
    return files


def _parse_regions(lines: list[str], path: Path) -> list[_Region]:
    """Walk a file's lines and extract every well-formed region.

    Raises ``_MarkerError`` (caught by every caller and converted to
    exit 5) if a region opens without a matching close, an end marker
    appears outside any open region, an end marker disagrees with its
    open marker's kind, or the line immediately after the start marker
    is not a ``<!-- template: ... -->`` comment. Catching these in the
    same walk keeps marker validation and drift detection on one parser.
    """
    for number, line in enumerate(lines, start=1):
        if "<!-- regen:panel-count-" in line:
            fragments = line.splitlines()
            if len(fragments) > 1 and any(
                _CONTROL_RE.fullmatch(part.rstrip()) for part in fragments
            ):
                raise _MarkerError(
                    f"{path}: line {number}: put the marker on its own physical line"
                )
    regions: list[_Region] = []
    i = 0
    n_lines = len(lines)
    while i < n_lines:
        line = lines[i]
        marker = _CONTROL_RE.fullmatch(line.rstrip())
        if marker and marker[2] == "end":
            raise _MarkerError(
                f"{path}: line {i + 1}: orphan end marker for "
                f"regen:panel-count-{marker[1]} (no matching start)"
            )
        if not marker:
            i += 1
            continue
        kind = marker[1]
        if i + 1 >= n_lines:
            raise _MarkerError(
                f"{path}: line {i + 1}: regen:panel-count-{kind}:start has no body "
                f"(template comment expected on next line)"
            )
        template_m = _TEMPLATE_RE.fullmatch(lines[i + 1].rstrip())
        if template_m is None:
            raise _MarkerError(
                f"{path}: line {i + 2}: expected <!-- template: ... --> directly after "
                f"regen:panel-count-{kind}:start, got: {lines[i + 1]!r}"
            )
        if i + 2 >= n_lines:
            raise _MarkerError(
                f"{path}: line {i + 2}: regen:panel-count-{kind}:start has template but "
                f"no rendered body line"
            )
        if i + 3 >= n_lines:
            raise _MarkerError(
                f"{path}: line {i + 1}: regen:panel-count-{kind}:start without matching :end marker"
            )
        for number, content in ((i + 2, template_m[1]), (i + 3, lines[i + 2])):
            if _CONTROL_RE.search(content) or _TEMPLATE_RE.search(content):
                raise _MarkerError(
                    f"{path}: line {number}: expected panel-count prose, found a marker"
                )
        end_line_m = _CONTROL_RE.fullmatch(lines[i + 3].rstrip())
        if end_line_m is None or end_line_m[2] != "end":
            raise _MarkerError(
                f"{path}: line {i + 4}: expected regen:panel-count-{kind}:end "
                f"after rendered body, got: {lines[i + 3]!r}"
            )
        if end_line_m.group(1) != kind:
            raise _MarkerError(
                f"{path}: line {i + 4}: end marker kind {end_line_m.group(1)!r} does not "
                f"match start marker kind {kind!r}"
            )
        regions.append(
            _Region(
                start_line=i,
                end_line=i + 3,
                kind=kind,
                template=template_m.group(1),
            )
        )
        i += 4
    return regions


class _MarkerError(Exception):
    """Raised when a corpus file has malformed or unbalanced region markers."""


def _read_lines(path: Path) -> list[str]:
    with path.open(newline="") as source:
        return source.readlines()


def _regenerate_lines(lines: list[str], panel_n: int, path: Path) -> str:
    """replace the body of each generated region, preserving its line ending."""
    for region in _parse_regions(lines, path):
        n = panel_n if region.kind == _KIND_TOTAL else panel_n + 1
        index = region.start_line + 2
        body = lines[index]
        ending = body[len(body.rstrip("\r\n")) :]
        lines[index] = _render_template(region.template, n) + ending
    return "".join(lines)


def _run_check_or_write(*, write: bool, manifest_path: Path, corpus_root: Path) -> int:
    try:
        manifest = load_manifest(manifest_path)
    except ManifestError as e:
        print(f"regen_panel_counts: manifest error: {e}", file=sys.stderr)
        return generator_io.MANIFEST_ERROR_EXIT
    panel_n = len(manifest.panel)

    drifted: list[Path] = []
    for path in _corpus_files(corpus_root):
        try:
            lines = _read_lines(path)
        except (OSError, UnicodeDecodeError) as e:
            print(f"regen_panel_counts: failed to read {path}: {e}", file=sys.stderr)
            return generator_io.MANIFEST_ERROR_EXIT
        current = "".join(lines)
        try:
            regenerated = _regenerate_lines(lines, panel_n, path)
        except _MarkerError as e:
            print(f"regen_panel_counts: {e}", file=sys.stderr)
            return generator_io.DRIFT_EXIT
        if current == regenerated:
            continue
        if write:
            generator_io.atomic_write(path, regenerated, newline="")
        else:
            generator_io.emit_drift_diff(path, current, regenerated)
            drifted.append(path)

    if not write and drifted:
        print(
            "\nregen_panel_counts: panel-count phrases are out of date in:\n  "
            + "\n  ".join(str(p) for p in drifted)
            + "\nRun scripts/regen.sh to regenerate.",
            file=sys.stderr,
        )
        return generator_io.DRIFT_EXIT
    return 0


def _run_validate_markers(*, corpus_root: Path) -> int:
    failures: list[str] = []
    for path in _corpus_files(corpus_root):
        try:
            lines = _read_lines(path)
        except (OSError, UnicodeDecodeError) as e:
            failures.append(f"{path}: failed to read: {e}")
            continue
        try:
            _parse_regions(lines, path)
        except _MarkerError as e:
            failures.append(str(e))
    if failures:
        print("regen_panel_counts: marker validation failed:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return generator_io.DRIFT_EXIT
    return 0


# match punctuation-led and wrapped counts without matching tokens such as B2.
_COVERAGE_BROAD_RE = re.compile(
    r"\b(?:(?i:panel\s+of|the\s+other|all)\s+)?\d+\s+(?:reviewer\s+)?personas?\b(?:\s+(?i:total)\b)?"
)

# total-shaped phrases must stay generated even when their counts currently match.
_COVERAGE_ALLOW_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\d+\s+personas?\s+(?:approved|objected|requested\s+changes|raised|flagged|agreed)"
    ),
    re.compile(r"agreed\s+by\s+\d+\s+personas?"),
    re.compile(r"\d+\s+Move\s+C\s+personas?"),
)


def _unwrapped_counts(paragraph: str) -> Iterator[re.Match[str]]:
    allowed_spans = [
        match.span()
        for pattern in _COVERAGE_ALLOW_PATTERNS
        for match in pattern.finditer(paragraph)
    ]
    for match in _COVERAGE_BROAD_RE.finditer(paragraph):
        if not any(start <= match.start() and match.end() <= end for start, end in allowed_spans):
            yield match


def _run_validate_coverage(*, corpus_root: Path) -> int:
    failures: list[str] = []
    for path in _corpus_files(corpus_root):
        try:
            lines = _read_lines(path)
        except (OSError, UnicodeDecodeError) as e:
            failures.append(f"{path}: failed to read: {e}")
            continue
        try:
            regions = _parse_regions(lines, path)
        except _MarkerError as e:
            failures.append(str(e))
            continue
        region_lines: set[int] = set()
        for r in regions:
            for j in range(r.start_line, r.end_line + 1):
                region_lines.add(j)
        # exclude generated regions while retaining line breaks for wrapped phrases.
        scan_lines = [
            "" if idx in region_lines else line.rstrip("\r\n") for idx, line in enumerate(lines)
        ]
        scan_text = "\n".join(scan_lines)
        line_number = 1
        # keep the delimiters so diagnostics retain physical line numbers.
        for paragraph in re.split(r"(\n[^\S\n]*\n)", scan_text):
            for m in _unwrapped_counts(paragraph):
                start_line = line_number + paragraph.count("\n", 0, m.start())
                failures.append(
                    f"{path}: line {start_line}: unhandled numbered persona-count phrase: "
                    f"{m.group(0)!r}\n"
                    f"    fix: wrap the phrase in a regen:panel-count region, OR add an "
                    f"allowlist pattern to _COVERAGE_ALLOW_PATTERNS in "
                    f"scripts/regen_panel_counts.py."
                )
            line_number += paragraph.count("\n")

    if failures:
        print("regen_panel_counts: coverage check failed:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return generator_io.DRIFT_EXIT
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="diff vs disk (default)")
    mode.add_argument("--write", action="store_true", help="rewrite files in place")
    mode.add_argument(
        "--validate-markers",
        action="store_true",
        help="check that every region's markers are balanced and well-formed",
    )
    mode.add_argument(
        "--validate-coverage",
        action="store_true",
        help="require every numbered persona-count phrase in the corpus to be "
        "wrapped in a regen region or to match an allowlist pattern",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "reviewers" / "personas.yaml",
    )
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repo root containing SKILL.md, tests/scenarios/, reviewers/ "
        "(default: detected from script path)",
    )
    args = parser.parse_args(argv)
    if not (args.write or args.validate_markers or args.validate_coverage):
        args.check = True

    if args.validate_markers:
        return _run_validate_markers(corpus_root=args.corpus_root)
    if args.validate_coverage:
        return _run_validate_coverage(corpus_root=args.corpus_root)

    return _run_check_or_write(
        write=args.write, manifest_path=args.manifest, corpus_root=args.corpus_root
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
