"""Helper imported by inline cog snippets to keep them short.

Cog runs inline Python from inside source files (e.g. SKILL.md). Those
snippets stay readable when they say `import _personas_for_cog as P;
P.panel()` rather than reproducing the manifest-loader plumbing.
"""

from __future__ import annotations

from pathlib import Path

from personas_manifest import load_manifest

_MANIFEST = load_manifest(Path(__file__).resolve().parent.parent / "reviewers" / "personas.yaml")


def panel():
    return _MANIFEST.panel


def adversary():
    return _MANIFEST.adversary
