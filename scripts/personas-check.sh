#!/usr/bin/env bash
# Compatibility entrypoint for scripts/regen-check.sh; see docs/generators.md.
set -euo pipefail
exec "$(dirname -- "$0")/regen-check.sh" "$@"
