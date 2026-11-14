#!/usr/bin/env bash
# count_new_loc.sh — count added LOC vs. base, excluding generated/lock/snapshot files.
#
# Usage:
#   count_new_loc.sh <base_branch>
#
# Output to stdout:
#   line 1: total added LOC after exclusions (integer)
#   line 2+: TSV of "<added>\t<deleted>\t<path>" for each INCLUDED file
#
# Output to stderr (diagnostics):
#   one line per excluded file, "# excluded: <path>" or "# excluded (binary): <path>".
#   Capture stderr separately if you need the exclusion list.
#
# Exits:
#   0 — counted successfully
#   1 — usage error
#   2 — git error (not a repo, base ref missing, etc.)

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <base_branch>" >&2
  exit 1
fi

BASE="$1"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not inside a git repository." >&2
  exit 2
fi

BASE_REF="origin/${BASE}"
if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  if git rev-parse --verify "$BASE" >/dev/null 2>&1; then
    BASE_REF="$BASE"
  else
    echo "ERROR: base ref '$BASE_REF' (and '$BASE') not found." >&2
    exit 2
  fi
fi

# is_excluded — return 0 if path should be excluded from the count.
is_excluded() {
  local path="$1"
  # depth-independent directory excludes (monorepo-safe)
  if [[ "$path" =~ (^|/)(vendor|node_modules|dist|build|\.next|__snapshots__)(/|$) ]]; then
    return 0
  fi
  case "$path" in
    # lock files
    package-lock.json | */package-lock.json) return 0 ;;
    yarn.lock | */yarn.lock) return 0 ;;
    pnpm-lock.yaml | */pnpm-lock.yaml) return 0 ;;
    Cargo.lock | */Cargo.lock) return 0 ;;
    Gemfile.lock | */Gemfile.lock) return 0 ;;
    poetry.lock | */poetry.lock) return 0 ;;
    composer.lock | */composer.lock) return 0 ;;
    go.sum | */go.sum) return 0 ;;
    Pipfile.lock | */Pipfile.lock) return 0 ;;
    *.lock) return 0 ;;
    # generated markers
    *.generated.*) return 0 ;;
    *.gen.go) return 0 ;;
    *_generated.go) return 0 ;;
    *.pb.go) return 0 ;;
    *.pb.ts) return 0 ;;
    # snapshots (extension-based)
    *.snap) return 0 ;;
  esac
  return 1
}

TOTAL=0
INCLUDED_LINES=""
EXCLUDED_LINES=""

while IFS=$'\t' read -r added deleted path; do
  # git diff --numstat emits renames as either
  #   "old/path => new/path"            (whole-path rename)
  # or
  #   "{old => new}/shared/suffix"      (partial-path rename)
  # collapse both to the post-rename path before exclusion matching and TSV emission.
  if [[ "$path" == *"{"*" => "*"}"* ]]; then
    path="${path/\{*\ =\>\ /}"
    path="${path/\}/}"
  elif [[ "$path" == *" => "* ]]; then
    path="${path##*\ =\>\ }"
  fi
  # binary diffs show as "-" for both added and deleted; skip them.
  if [[ "$added" == "-" || "$deleted" == "-" ]]; then
    EXCLUDED_LINES+="# excluded (binary): $path"$'\n'
    continue
  fi
  if is_excluded "$path"; then
    EXCLUDED_LINES+="# excluded: $path"$'\n'
    continue
  fi
  TOTAL=$((TOTAL + added))
  INCLUDED_LINES+="${added}"$'\t'"${deleted}"$'\t'"${path}"$'\n'
done < <(git -c core.quotepath=false diff --numstat "${BASE_REF}...HEAD")

printf '%s\n' "$TOTAL"
if [[ -n "$INCLUDED_LINES" ]]; then
  printf '%s' "$INCLUDED_LINES"
fi
if [[ -n "$EXCLUDED_LINES" ]]; then
  printf '%s' "$EXCLUDED_LINES" >&2
fi
