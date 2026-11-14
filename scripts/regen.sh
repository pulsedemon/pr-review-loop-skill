#!/usr/bin/env bash
# Regenerate persona-derived surfaces from reviewers/personas.yaml.
# Currently manages:
#   - SKILL.md "Reviewer personas" bullet list (via cog)
#   - SKILL.md §4b Move A/A.1/B/C bullets (via cog,
#     scripts/_move_c_bullet_for_cog.py, from the move_* manifest flags)
#   - reviewers/output.schema.json `reviewer` enum (via regen_schema_enum.py)
#   - panel-count phrases across SKILL.md, tests/scenarios/*.md, reviewers/*.md
#     (via regen_panel_counts.py)
#   - Move A.1 sub-mechanic enum across SKILL.md, state.schema.json,
#     output.schema.json, reviewers/tests.md, reviewers/adversary.md
#     (via regen_move_a1_enum.py, sourced from manifests/move-a1-enum.yaml)
#   - §4d.0 adversary cap mirrors (via regen_adversary_caps.py, sourced
#     from manifests/adversary-caps.yaml)
#   - dev-tree skip lists across install.sh, tests/run.sh, test_helper.bash
#     and regen_move_a1_enum.py (via regen_dev_trees.py, sourced from
#     manifests/dev-trees.yaml)
#
# See docs/editing-personas.md.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python3 -m cogapp -r -I "$ROOT/scripts" @"$ROOT/scripts/cogfiles.txt"
python3 "$ROOT/scripts/regen_schema_enum.py" --write
python3 "$ROOT/scripts/regen_panel_counts.py" --write
python3 "$ROOT/scripts/regen_move_a1_enum.py" --write
python3 "$ROOT/scripts/regen_adversary_caps.py" --write
python3 "$ROOT/scripts/regen_dev_trees.py" --write
