"""Scenario manifest loader.

Source of truth: tests/scenarios/manifest.yaml. Every scenario-status sync
test consumes derived lists from here so one edit updates the repo-wide view
of which scenarios are CI-trusted, manually validated, or still design-only.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
_TIERS = frozenset({"ci_trusted", "manual_validated", "design_only"})
_FILE_RE = re.compile(r"^(?P<number>\d{2})-.+\.md$")
_LIST_TIER_MAP = {
    "ci-files": "ci_trusted",
    "manual-files": "manual_validated",
    "design-files": "design_only",
}


class ManifestError(ValueError):
    """Raised when tests/scenarios/manifest.yaml is malformed."""


@dataclass(frozen=True)
class Scenario:
    number: int
    file: str
    title: str
    tier: str
    reason: str
    proof_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ManifestError(f"scenario number must be >= 1, got {self.number}")
        match = _FILE_RE.match(self.file)
        if not match:
            raise ManifestError(
                f"file {self.file!r} must match NN-name.md so sync tests can locate it"
            )
        expected_prefix = f"{self.number:02d}-"
        if not self.file.startswith(expected_prefix):
            raise ManifestError(f"file {self.file!r} must start with {expected_prefix!r}")
        if self.tier not in _TIERS:
            raise ManifestError(f"tier {self.tier!r} is invalid (allowed: {sorted(_TIERS)})")
        if not self.title.strip():
            raise ManifestError(f"{self.file}: title must be non-empty")
        if not self.reason.strip():
            raise ManifestError(f"{self.file}: reason must be non-empty")
        if self.tier == "ci_trusted" and not self.proof_sources:
            raise ManifestError("ci_trusted scenarios must define proof_sources")
        if self.tier != "ci_trusted" and self.proof_sources:
            raise ManifestError(f"{self.file}: only ci_trusted scenarios may define proof_sources")
        for proof in self.proof_sources:
            if not proof.strip():
                raise ManifestError(f"{self.file}: proof_sources entries must be non-empty")


@dataclass(frozen=True)
class Manifest:
    scenarios: tuple[Scenario, ...]

    def __post_init__(self) -> None:
        if not self.scenarios:
            raise ManifestError("manifest scenarios list must be non-empty")
        seen_numbers: set[int] = set()
        seen_files: set[str] = set()
        previous = 0
        for scenario in self.scenarios:
            if scenario.number in seen_numbers:
                raise ManifestError(f"duplicate scenario number: {scenario.number}")
            if scenario.file in seen_files:
                raise ManifestError(f"duplicate scenario file: {scenario.file}")
            if scenario.number <= previous:
                raise ManifestError("scenario numbers must be strictly increasing")
            seen_numbers.add(scenario.number)
            seen_files.add(scenario.file)
            previous = scenario.number

    def by_number(self, number: int) -> Scenario:
        for scenario in self.scenarios:
            if scenario.number == number:
                return scenario
        raise ManifestError(f"unknown scenario number: {number}")

    def by_file(self, file: str) -> Scenario:
        for scenario in self.scenarios:
            if scenario.file == file:
                return scenario
        raise ManifestError(f"unknown scenario file: {file}")

    def by_tier(self, tier: str) -> tuple[Scenario, ...]:
        return tuple(scenario for scenario in self.scenarios if scenario.tier == tier)


def _validate_proof_source(scenario_file: str, proof: str) -> str:
    proof = proof.strip()
    if not proof:
        raise ManifestError(f"{scenario_file}: proof_sources entries must be non-empty")
    raw_path = Path(proof)
    if raw_path.is_absolute():
        raise ManifestError(f"{scenario_file}: proof source {proof!r} must be repo-relative")
    try:
        resolved = (REPO_ROOT / raw_path).resolve()
        resolved.relative_to(REPO_ROOT)
    except (OSError, ValueError) as exc:
        raise ManifestError(
            f"{scenario_file}: proof source {proof!r} must stay within the repo root"
        ) from exc
    return proof


def _parse_scenario(path: Path, index: int, raw: object) -> Scenario:
    label = f"scenarios[{index}]"
    if not isinstance(raw, dict):
        raise ManifestError(f"{path}: {label} must be a mapping, got {type(raw).__name__}")
    required = {"number", "file", "title", "tier", "reason"}
    missing = sorted(required - set(raw))
    if missing:
        raise ManifestError(f"{path}: {label} missing required key(s): {', '.join(missing)}")
    extra = sorted(set(raw) - (required | {"proof_sources"}))
    if extra:
        raise ManifestError(f"{path}: {label} has unknown key(s): {', '.join(extra)}")
    number = raw["number"]
    if not isinstance(number, int) or isinstance(number, bool):
        raise ManifestError(f"{path}: {label}.number must be an integer")
    file = raw["file"]
    title = raw["title"]
    tier = raw["tier"]
    reason = raw["reason"]
    if not isinstance(file, str):
        raise ManifestError(f"{path}: {label}.file must be a string")
    if not isinstance(title, str):
        raise ManifestError(f"{path}: {label}.title must be a string")
    if not isinstance(tier, str):
        raise ManifestError(f"{path}: {label}.tier must be a string")
    if not isinstance(reason, str):
        raise ManifestError(f"{path}: {label}.reason must be a string")
    proof_sources_raw = raw.get("proof_sources", [])
    if not isinstance(proof_sources_raw, list):
        raise ManifestError(f"{path}: {label}.proof_sources must be a list")
    proof_sources: list[str] = []
    for proof_index, proof in enumerate(proof_sources_raw):
        if not isinstance(proof, str):
            raise ManifestError(f"{path}: {label}.proof_sources[{proof_index}] must be a string")
        proof_sources.append(_validate_proof_source(file, proof))
    return Scenario(
        number=number,
        file=file,
        title=title.strip(),
        tier=tier.strip(),
        reason=reason.strip(),
        proof_sources=tuple(proof_sources),
    )


def load_manifest(path: Path) -> Manifest:
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise ManifestError(f"failed to read {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestError(f"failed to parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: top level must be a mapping")
    scenarios_raw = data.get("scenarios")
    if not isinstance(scenarios_raw, list) or not scenarios_raw:
        raise ManifestError(f"{path}: 'scenarios' must be a non-empty list")
    scenarios = tuple(_parse_scenario(path, index, raw) for index, raw in enumerate(scenarios_raw))
    return Manifest(scenarios=scenarios)


def _default_manifest_path() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "scenarios" / "manifest.yaml"


def _list_output(manifest: Manifest, list_name: str) -> Iterable[str]:
    if list_name == "all-files":
        return (scenario.file for scenario in manifest.scenarios)
    if list_name == "tier-map":
        return (f"{scenario.file}|{scenario.tier}" for scenario in manifest.scenarios)
    tier = _LIST_TIER_MAP[list_name]
    return (scenario.file for scenario in manifest.by_tier(tier))


def _proof_sources_for(manifest: Manifest, scenario_file: str) -> tuple[str, ...]:
    scenario = manifest.by_file(scenario_file)
    if scenario.tier != "ci_trusted":
        raise ManifestError(f"{scenario.file} is not ci_trusted")
    return scenario.proof_sources


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Scenario manifest CLI for bats consumers.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_default_manifest_path(),
        help="path to tests/scenarios/manifest.yaml",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--list",
        choices=["all-files", "ci-files", "manual-files", "design-files", "tier-map"],
        help="which derived list to print, one item per line",
    )
    group.add_argument(
        "--proof-sources-for",
        metavar="SCENARIO_FILE",
        help="print proof sources for one ci_trusted scenario file, one per line",
    )
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 3
    if args.list is not None:
        for line in _list_output(manifest, args.list):
            print(line)
    else:
        try:
            proof_sources = _proof_sources_for(manifest, args.proof_sources_for)
        except ManifestError as exc:
            print(str(exc), file=sys.stderr)
            return 4
        for proof in proof_sources:
            print(proof)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
