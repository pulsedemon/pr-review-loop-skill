#!/usr/bin/env bash
# tests/run.sh — run all bats tests for the skill.
#
# Requires:
#   - bats-core (`bats --version` >= 1.7)
#   - python3 with pyyaml, jsonschema, and cogapp (for validate_metadata.py /
#     validate_reviewer_output.py / scripts/regen-check.sh)
#   - jq, git
#
# Exit codes are bats' exit codes (0 on success, non-zero on any failure).

set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)

if ! command -v bats >/dev/null 2>&1; then
  echo "ERROR: bats not installed. Install bats-core:" >&2
  echo "  macOS:   brew install bats-core" >&2
  echo "  Ubuntu:  sudo apt-get install -y bats" >&2
  echo "  source:  https://github.com/bats-core/bats-core" >&2
  exit 2
fi

# Require bats-core >= 1.7 to match the header contract. Older distro packages
# (e.g. Ubuntu 20.04's `bats` 1.2.x) fail later with less actionable errors.
bats_version=$(bats --version 2>/dev/null | awk '{print $NF}')
if [[ -z "$bats_version" ]]; then
  echo "ERROR: could not determine bats version from \`bats --version\`." >&2
  exit 2
fi
bats_major=${bats_version%%.*}
bats_rest=${bats_version#*.}
bats_minor=${bats_rest%%.*}
if ! [[ "$bats_major" =~ ^[0-9]+$ && "$bats_minor" =~ ^[0-9]+$ ]]; then
  echo "ERROR: unrecognized bats version string: $bats_version" >&2
  exit 2
fi
if ((bats_major < 1)) || { ((bats_major == 1)) && ((bats_minor < 7)); }; then
  echo "ERROR: bats-core >= 1.7 required (found $bats_version)." >&2
  exit 2
fi

# cogapp is required by scripts/regen-check.sh, invoked from
# tests/bats/test_persona_surfaces_generator_check.bats. Catch the
# missing-dependency case here with the same shape of install hint
# we give for bats, rather than surfacing a Python ImportError mid-suite.
if ! python3 -c "import cogapp" >/dev/null 2>&1; then
  echo "ERROR: cogapp not installed (used by scripts/regen-check.sh)." >&2
  echo "  pip:  pip install cogapp" >&2
  echo "  uv:   uv sync   # if the repo uses uv-managed dev deps" >&2
  exit 2
fi

# GNU parallel is required for `bats --jobs` below. Without it, bats prints a
# one-line warning and runs ZERO tests while still exiting non-zero — an
# unmistakable failure, but an unhelpful one. Catch it here with an
# actionable install hint instead.
if ! command -v parallel >/dev/null 2>&1; then
  echo "ERROR: GNU parallel not installed (required for parallel bats runs)." >&2
  echo "  macOS:   brew install parallel" >&2
  echo "  Ubuntu:  sudo apt-get install -y parallel" >&2
  exit 2
fi

# drift guard: matcher rule prose lives only in docs/synthesis.md.
# a copy in SKILL.md would let the two drift; fail fast here.
SKILL_MD="${HERE}/../SKILL.md"
if [[ ! -r "$SKILL_MD" ]]; then
  echo "ERROR: SKILL.md missing or unreadable; drift guard cannot run." >&2
  exit 3
fi
# tolerate spacing and 0.6 / .6 / 0.60 variants so the guard doesn't lapse
# on superficial rewrites.
drift_rc=0
grep -qE 'token_overlap[[:space:]]*>=?[[:space:]]*0?\.60?' "$SKILL_MD" || drift_rc=$?
if ((drift_rc == 0)); then
  echo "ERROR: SKILL.md contains the matcher rule (token_overlap threshold)." >&2
  echo "  This rule belongs only in docs/synthesis.md (see Scenario 22)." >&2
  exit 3
elif ((drift_rc != 1)); then
  echo "ERROR: drift-guard grep failed (rc=$drift_rc) against $SKILL_MD." >&2
  exit 3
fi

# drift guard: §4d.0 cap literal (2) must only appear next to the cap field
# names (shallow_adversary_runs / shallow_approval_adversary_runs) in the
# files listed in ALLOWED_CAP_PATHS below — docs/adversary.md (canonical
# prose), templates/state.schema.json (schema-enforced source of truth),
# and tests/run.sh itself (which hosts the regex definition + examples).
# scripts/_adversary_caps.sh also holds the literal (`readonly ADVERSARY_CAP=2`)
# but is not a field-name match, so the regex never reaches it.
# Prose elsewhere should use ADVERSARY_CAP or refer to "the cap" by name.
#
# The following path prefixes are excluded (post-filter, anchored to the
# repo root — not basename matches, which would also exclude sibling dirs of
# the same name):
#   docs/superpowers/      — frozen historical plans/specs from past sessions
#   tests/scenarios/       — manual test fixtures asserting specific state
#                            values at the cap boundary; these are test
#                            expectations, not contract prose.
#   tools/recall-harness/  — offline-refreshed CI artifact; may quote cap
#                            literals when explaining real-miss findings, not
#                            contract prose.
REPO_ROOT="$(cd "${HERE}/.." && pwd)"
ALLOWED_CAP_PATHS=(
  "${REPO_ROOT}/docs/adversary.md"
  "${REPO_ROOT}/templates/state.schema.json"
  # tests/run.sh itself: the regex definition and its documentation examples
  # appear here by necessity; they are the guard, not a violation.
  "${REPO_ROOT}/tests/run.sh"
)
EXCLUDED_CAP_PREFIXES=(
  "docs/superpowers/"
  "tests/scenarios/"
  "tools/recall-harness/"
)
# match the field name followed within ~40 chars by a comparison to 2:
#   shallow_adversary_runs < 2          (incl. end-of-line)
#   shallow_approval_adversary_runs == 2
#   shallow_adversary_runs<2            (zero-space, single-char operator)
#   shallow_adversary_runs.*<= 2
#   shallow_adversary_runs >= 2
# The `{0,40}` (not {1,40}) admits zero-space variants where the operator
# follows the field name with no separator. The trailing `($|[^0-9])` keeps
# "2" from matching "20"/"21"/etc. while still catching cap-comparisons that
# end the line.
# Blind spot: drift phrased without a comparison operator ("capped at 2",
# "reaches 2", "bounded by 2") slips through. The schema `maximum: 2` is
# the only true enforcement; this guard is an operator-anchored style check.
CAP_REGEX='shallow_(adversary|approval_adversary)_runs[^A-Za-z0-9_]{0,40}[<>=]{1,2}[[:space:]]*=?[[:space:]]*2($|[^0-9])'
cap_fail=0
cap_grep_rc=0
# Run grep from REPO_ROOT so hit paths are repo-relative (`./foo/bar:N:…`).
# `cd` is on its own statement; under `set -e` a failure aborts loudly rather
# than being captured as a "grep found nothing" rc=1 by `|| cap_grep_rc=$?`.
cd "$REPO_ROOT"
# Dev-only trees the cap-drift grep must not descend into. Generated from
# manifests/dev-trees.yaml; an array rather than inline flags because a cog
# marker inside a backslash-continued command would terminate the continuation.
# [[[cog: dev_trees_grep ]]]
CAP_GREP_EXCLUDES=(
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=.pytest_cache --exclude-dir=.ruff_cache
  --exclude-dir=.worktrees --exclude-dir=worktrees --exclude-dir=__pycache__ --exclude-dir=.DS_Store
  --exclude-dir=.claude --exclude-dir=.superpowers
)
# [[[end]]]
cap_hits=$(
  grep -RnE --include='*.md' --include='*.json' --include='*.sh' --include='*.py' --include='*.yaml' --include='*.yml' \
    "${CAP_GREP_EXCLUDES[@]}" \
    "$CAP_REGEX" .
) || cap_grep_rc=$?
if ((cap_grep_rc != 0 && cap_grep_rc != 1)); then
  echo "ERROR: cap-drift grep failed (rc=$cap_grep_rc)." >&2
  exit 3
fi
while IFS= read -r hit; do
  [[ -z "$hit" ]] && continue
  hit_path="${hit%%:*}"
  rel="${hit_path#./}"
  abs="${REPO_ROOT}/${rel}"
  # path-anchored exclusion: prefix must match from the repo root, not any
  # nested directory with a colliding basename.
  excluded=0
  for p in "${EXCLUDED_CAP_PREFIXES[@]}"; do
    if [[ "$rel" == "$p"* ]]; then
      excluded=1
      break
    fi
  done
  if ((excluded == 1)); then
    continue
  fi
  allowed=0
  for a in "${ALLOWED_CAP_PATHS[@]}"; do
    if [[ "$abs" == "$a" ]]; then
      allowed=1
      break
    fi
  done
  if ((allowed == 0)); then
    if ((cap_fail == 0)); then
      echo "ERROR: adversary cap literal (2) appears next to cap field name outside allowed files." >&2
      echo "  Allowed prose homes for '<field> <op> 2' literals:" >&2
      echo "    docs/adversary.md (canonical prose)," >&2
      echo "    templates/state.schema.json (schema 'maximum')," >&2
      echo "    tests/run.sh (this guard's regex + examples)." >&2
      echo "  The literal also lives in scripts/_adversary_caps.sh (readonly ADVERSARY_CAP=2)." >&2
      echo "  Elsewhere, use ADVERSARY_CAP or refer to 'the cap' by name." >&2
    fi
    echo "  $hit" >&2
    cap_fail=1
  fi
done <<<"$cap_hits"
if ((cap_fail == 1)); then
  exit 3
fi
# Positive control: pin the count of CAP_REGEX matches in tests/run.sh
# (currently 5, all in the block comment immediately above CAP_REGEX).
# Those examples are the canonical paraphrases the guard is meant to catch;
# a regex refactor that breaks them turns the guard into a no-op, and a
# count-pin (vs a bare `grep -q`) additionally catches new cap-literal
# prose added elsewhere in this file — which the whole-file allow-list
# (ALLOWED_CAP_PATHS) would otherwise mask.
EXPECTED_RUN_SH_CAP_MATCHES=5
run_sh_cap_matches=$(grep -cE "$CAP_REGEX" "${REPO_ROOT}/tests/run.sh")
if ((run_sh_cap_matches != EXPECTED_RUN_SH_CAP_MATCHES)); then
  echo "ERROR: tests/run.sh has ${run_sh_cap_matches} CAP_REGEX matches; expected ${EXPECTED_RUN_SH_CAP_MATCHES}." >&2
  echo "       Either the regex examples in the CAP_REGEX block comment changed" >&2
  echo "       (update EXPECTED_RUN_SH_CAP_MATCHES) or new cap-literal prose was" >&2
  echo "       added to this file (move it to docs/adversary.md or reword to" >&2
  echo "       use ADVERSARY_CAP / 'the cap')." >&2
  exit 3
fi

# Run the suite in parallel across files (--no-parallelize-within-files):
# bats hands each of the ~40 *.bats files to GNU parallel, but tests inside
# a file still run serially.
#
# This is deliberate. bats' default --jobs also parallelizes *within* files,
# routing every one of the ~380 individual tests through `parallel` — and
# the per-test fork/IPC overhead then exceeds the work each test does.
# Measured on this suite: plain `--jobs 2` ran 151s (vs 80s serial), a near-
# 2x *regression*; `--jobs 2 --no-parallelize-within-files` ran 46s. The
# across-files-only mode wins at every core count, including 2-core CI.
#
# nproc on Linux, sysctl on macOS; fall back to 4 if neither is available.
jobs=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
exec bats --jobs "$jobs" --no-parallelize-within-files "${HERE}/bats"
