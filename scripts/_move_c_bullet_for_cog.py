"""render SKILL.md's procedure moves from the persona manifest.

read assertion enum values from their manifest so both generators agree.
keep all moves in one cog block to stay within the skill's line limit.
"""

from __future__ import annotations

from pathlib import Path

from personas_manifest import load_manifest
from regen_move_a1_enum import load_values, render_value_list

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_MANIFEST = _REPO_ROOT / "reviewers" / "personas.yaml"
_A1_ENUM_MANIFEST = _REPO_ROOT / "manifests" / "move-a1-enum.yaml"

# spelled out to match the surrounding prose; the enum has never come
# close to the end of this list.
_NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")

_A1_REGION_START = "<!-- regen:move-a1-enum:start -->"
_A1_REGION_END = "<!-- regen:move-a1-enum:end -->"


def _joined(personas: list, adversary_name: str) -> str:
    """Backticked comma list. A single name keeps the ``\\`x\\` only`` phrasing."""
    names = sorted(p.name for p in personas if p.name != adversary_name)
    if not names:
        return ""
    backticked = ", ".join(f"`{n}`" for n in names)
    return f"{backticked} only" if len(names) == 1 else backticked


def _spell(n: int) -> str:
    return _NUMBER_WORDS[n] if n < len(_NUMBER_WORDS) else str(n)


def _move_a(names: str) -> str:
    return (
        f"- **Move A (test-intent audit)**, {names}: for each new/modified test, "
        f"verify the assertion exercises the behavior the name claims."
    )


def _move_a1(names: str) -> str:
    # the count is derived, not written: the enum is closed but not frozen,
    # and prose saying "five" would rot the next time a value is added.
    values = load_values(_A1_ENUM_MANIFEST)
    return (
        f"- **Move A.1 (assertion-vacuity audit)**, {names}: for each assertion, "
        f"check whether it's syntactically determinable to be vacuous via one of "
        f"{_spell(len(values))} sub-mechanics "
        f"({_A1_REGION_START}{render_value_list(values)}{_A1_REGION_END}); set "
        f"`move_a1_pattern` on each finding. See `reviewers/tests.md`."
    )


def _move_b(names: str) -> str:
    return (
        f"- **Move B (second-instance sweep)**, {names}: after a syntactically "
        f"findable finding, grep the diff for other instances of the same pattern and "
        f"raise one finding per instance. Each Move-B finding sets `move_b_pattern: "
        f'"<one-phrase pattern name>"`.'
    )


def _move_c(names: str, owner: str) -> str:
    return (
        f"- **Move C (cross-doc consistency)**, {names}: when the diff touches "
        f"both a doc and a spec, flag terminology drift (blocker) and contract drift "
        f"(suggestion; blocker if doc-as-contract; schema-constraint bullet always "
        f"suggestion, and the finding must cross-reference `{owner}` in `detail` "
        f"so synthesis can dedupe; `{owner}` owns the blocker for that pattern)."
    )


def render(manifest_path: str | Path | None = None) -> str:
    """return carried move bullets without a trailing newline.

    cog adds the final newline when it inserts the generated region.
    """
    path = Path(manifest_path) if manifest_path is not None else _DEFAULT_MANIFEST
    manifest = load_manifest(path)
    adversary = manifest.adversary.name

    bullets = [
        template(names)
        for template, names in (
            (_move_a, _joined(manifest.move_a_personas(), adversary)),
            (_move_a1, _joined(manifest.move_a1_personas(), adversary)),
            (_move_b, _joined(manifest.move_b_personas(), adversary)),
        )
        if names
    ]
    move_c_names = _joined(manifest.move_c_personas(), adversary)
    if move_c_names:
        bullets.append(_move_c(move_c_names, manifest.schema_constraint_owner().name))
    return "\n".join(bullets)
