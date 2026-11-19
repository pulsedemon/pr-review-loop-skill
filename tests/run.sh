#!/usr/bin/env bash
# tests/run.sh: run the drift guards, then every bats test for the skill.
#
# requires:
#   - bats-core >= 1.7 and GNU parallel
#   - python3 with the pyproject.toml dev dependency group (`uv sync`)
#   - jq, git, rsync
#
# exit codes: 1 if the cap-manifest read fails; 2 for the existing bats,
# cogapp or GNU parallel prerequisite checks; 3 for a drift-guard failure;
# otherwise bats' exit code.

set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)

if ! command -v bats >/dev/null 2>&1; then
  echo "ERROR: bats not installed. Install bats-core:" >&2
  echo "  macOS:   brew install bats-core" >&2
  echo "  Ubuntu:  sudo apt-get install -y bats" >&2
  echo "  source:  https://github.com/bats-core/bats-core" >&2
  exit 2
fi

# older distro packages fail later with less actionable errors.
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

# report missing cogapp before generator checks fail with an ImportError.
if ! python3 -c "import cogapp" >/dev/null 2>&1; then
  echo "ERROR: cogapp not installed (used by scripts/regen-check.sh)." >&2
  echo "  pip:  pip install cogapp" >&2
  echo "  uv:   uv sync" >&2
  exit 2
fi

# without GNU parallel, bats can fail before running any tests.
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
  echo "  This rule belongs only in docs/synthesis.md (see tests/scenarios/22-skill-split-anchors.md)." >&2
  exit 3
elif ((drift_rc != 1)); then
  echo "ERROR: drift-guard grep failed (rc=$drift_rc) against $SKILL_MD." >&2
  exit 3
fi

# comparisons use the manifest cap only in canonical prose and the generated
# schema maximum. other prose names "the cap" so manifest changes do not
# leave old values.
#
# exclusions are repo-relative prefixes so same-named siblings stay scanned:
# historical plans, scenario expectations and local recall reports may quote
# cap values without defining the runtime contract.
REPO_ROOT="$(cd "${HERE}/.." && pwd)"
cap=$(python3 -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["cap"])' \
  "${REPO_ROOT}/manifests/adversary-caps.yaml")
ALLOWED_CAP_PATHS=(
  "${REPO_ROOT}/docs/adversary.md"
  "${REPO_ROOT}/templates/state.schema.json"
)
EXCLUDED_CAP_PREFIXES=(
  "docs/superpowers/"
  "tests/scenarios/"
  "tools/recall-harness/"
)
# printf format for the field name followed within ~40 chars by a comparison
# to the cap. with N for the cap it matches:
#   shallow_adversary_runs < N          (incl. end-of-line)
#   shallow_approval_adversary_runs == N
#   shallow_adversary_runs<N            (zero-space, single-char operator)
#   shallow_adversary_runs.*<= N
#   shallow_adversary_runs >= N
# {0,40} admits zero-space comparisons; ($|[^0-9]) stops the cap matching
# a longer number while allowing a comparison at the end of a line.
# blind spot: operator-free phrases such as "capped at N" are not matched.
CAP_REGEX_FORMAT='shallow_(adversary|approval_adversary)_runs[^A-Za-z0-9_]{0,40}[<>=]{1,2}[[:space:]]*=?[[:space:]]*%s($|[^0-9])'
printf -v cap_regex "$CAP_REGEX_FORMAT" "$cap"
cap_fail=0
cap_grep_rc=0
# run grep from REPO_ROOT so hit paths are repo-relative (`./foo/bar:N:…`).
# `cd` is on its own statement; under `set -e` a failure aborts loudly rather
# than being captured as a "grep found nothing" rc=1 by `|| cap_grep_rc=$?`.
cd "$REPO_ROOT"
# dev-only trees the cap-drift grep must not descend into. generated from
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
    "$cap_regex" .
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
      echo "ERROR: adversary cap literal (${cap}) appears next to cap field name outside allowed files." >&2
      echo "  Allowed prose homes for '<field> <op> ${cap}' literals:" >&2
      echo "    docs/adversary.md (canonical prose)," >&2
      echo "    templates/state.schema.json (schema 'maximum')." >&2
      echo "  Elsewhere, refer to 'the cap' by name." >&2
    fi
    echo "  $hit" >&2
    cap_fail=1
  fi
done <<<"$cap_hits"
if ((cap_fail == 1)); then
  exit 3
fi
# a regex refactor that stops matching the N examples turns the guard into
# a no-op, so pin their count separately from real cap comparisons.
EXPECTED_RUN_SH_CAP_MATCHES=5
printf -v example_regex "$CAP_REGEX_FORMAT" N
run_sh_cap_matches=$(grep -cE "$example_regex" "${REPO_ROOT}/tests/run.sh" || true)
if ((run_sh_cap_matches != EXPECTED_RUN_SH_CAP_MATCHES)); then
  echo "ERROR: tests/run.sh has ${run_sh_cap_matches} CAP_REGEX_FORMAT example matches; expected ${EXPECTED_RUN_SH_CAP_MATCHES}." >&2
  echo "       Either the examples in the CAP_REGEX_FORMAT comment changed" >&2
  echo "       (update EXPECTED_RUN_SH_CAP_MATCHES) or the format no longer matches them." >&2
  exit 3
fi

# one GNU parallel job per file avoids process startup for every test.
jobs=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
exec bats --jobs "$jobs" --no-parallelize-within-files "${HERE}/bats"
