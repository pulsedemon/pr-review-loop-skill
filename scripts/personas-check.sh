#!/usr/bin/env bash
# Back-compat shim — see docs/generators.md.
# Removed in the Tier 3 PR; any caller hard-coding `personas-check.sh` will
# break then. Future generators that introspect $0 must reach
# scripts/regen-check.sh directly, not via this shim.
set -euo pipefail
exec "$(dirname -- "$0")/regen-check.sh" "$@"
