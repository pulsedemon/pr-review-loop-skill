"""Helper imported by inline cog snippets to keep them short.

Cog runs inline Python from inside source files (e.g. SKILL.md). Those
snippets stay readable when they say `import _personas_for_cog as P;
P.panel()` rather than reproducing the manifest-loader plumbing.

Adds the repo's `scripts/` dir to sys.path on import so cog can find
`personas_manifest` regardless of where cog is invoked from.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personas_manifest import load_manifest  # noqa: E402

_MANIFEST = load_manifest(_SCRIPTS.parent / "reviewers" / "personas.yaml")


def panel():
    return _MANIFEST.panel


def adversary():
    return _MANIFEST.adversary
