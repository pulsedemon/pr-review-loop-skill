"""Make scripts/personas_manifest.py importable as a top-level module from tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
