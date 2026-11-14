#!/usr/bin/env bash
# Check that persona-derived surfaces are up to date with
# reviewers/personas.yaml. Exits non-zero with a unified diff if not.
#
# CI gate; the developer-facing companion is scripts/regen.sh.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python3 -m cogapp --check --diff \
  --check-fail-msg "Run scripts/regen.sh to regenerate persona-derived surfaces from reviewers/personas.yaml." \
  -I "$ROOT/scripts" \
  @"$ROOT/scripts/cogfiles.txt"

python3 "$ROOT/scripts/regen_schema_enum.py" --check
python3 "$ROOT/scripts/regen_panel_counts.py" --check
python3 "$ROOT/scripts/regen_panel_counts.py" --validate-markers
python3 "$ROOT/scripts/regen_panel_counts.py" --validate-coverage
python3 "$ROOT/scripts/regen_move_a1_enum.py" --check
python3 "$ROOT/scripts/regen_adversary_caps.py" --check
python3 "$ROOT/scripts/regen_dev_trees.py" --check
