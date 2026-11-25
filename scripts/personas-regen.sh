#!/usr/bin/env bash
# Compatibility entrypoint for scripts/regen.sh; see docs/generators.md.
set -euo pipefail
exec "$(dirname -- "$0")/regen.sh" "$@"
