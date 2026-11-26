#!/usr/bin/env bash
# Regenerate every manifest-derived surface. With --check, change nothing and
# exit 5 when a surface is out of date. GENERATORS and scripts/cogfiles.txt
# are the surface list; see docs/generators.md.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

GENERATORS=(
  regen_schema_enum.py
  regen_panel_counts.py
  regen_move_a1_enum.py
  regen_adversary_caps.py
  regen_dev_trees.py
)

if [[ "${1:-}" == "--check" ]]; then
  # cog prints its diff on stdout; the generator contract puts drift on stderr.
  PYTHONIOENCODING=utf-8 python3 -m cogapp --check --diff \
    --check-fail-msg "Run scripts/regen.sh to regenerate the cog-managed surfaces." \
    -I "$ROOT/scripts" @"$ROOT/scripts/cogfiles.txt" >&2
  for generator in "${GENERATORS[@]}"; do
    python3 "$ROOT/scripts/$generator" --check
  done
  python3 "$ROOT/scripts/regen_panel_counts.py" --validate-markers
  python3 "$ROOT/scripts/regen_panel_counts.py" --validate-coverage
else
  python3 -m cogapp -r -I "$ROOT/scripts" @"$ROOT/scripts/cogfiles.txt"
  for generator in "${GENERATORS[@]}"; do
    python3 "$ROOT/scripts/$generator" --write
  done
fi
