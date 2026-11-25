#!/usr/bin/env bash
# CI entrypoint for scripts/regen.sh --check.
set -euo pipefail
exec "$(dirname -- "$0")/regen.sh" --check
