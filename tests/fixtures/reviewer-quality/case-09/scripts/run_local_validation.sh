#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f package.json ]]; then
  printf '%s\n' '# no recognized stack' >&2
  exit 2
fi

printf '%s\n' '# stack: node' >&2
if ! command -v npm >/dev/null 2>&1; then
  printf '%s\n' '# skip: npm not on PATH' >&2
  exit 0
fi

npm test || exit 3
