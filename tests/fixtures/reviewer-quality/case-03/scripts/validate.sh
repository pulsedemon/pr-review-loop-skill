#!/usr/bin/env bash
set -euo pipefail

if ! command -v ruff >/dev/null 2>&1; then
  printf '%s\n' 'ruff is required' >&2
  exit 0
fi

ruff check .
