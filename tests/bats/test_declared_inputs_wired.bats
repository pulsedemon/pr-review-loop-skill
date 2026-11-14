#!/usr/bin/env bats

# Every input declared in SKILL.md "## Inputs" must be referenced somewhere the
# loop actually reads: elsewhere in SKILL.md, in docs/, or in scripts/.
#
# This exists because `dry_run` shipped declared-but-dead — named in the input
# list, in an invocation example, and in the README, but branched on nowhere, so
# the documented "review only, no commits" run committed and pushed. A
# declaration reads as a working feature; nothing failed when it wasn't one.

load test_helper

declared_inputs() {
  awk '/^## Inputs$/{f=1;next} /^## /{f=0} f' "${REPO_ROOT}/SKILL.md" |
    grep -oE '^- \*\*[a-z_]+\*\*' | sed 's/^- \*\*\(.*\)\*\*$/\1/'
}

@test "SKILL.md Inputs section is parseable and non-empty" {
  local count
  count="$(declared_inputs | wc -l | tr -d ' ')"
  [[ "$count" -gt 0 ]]
}

@test "every declared input is referenced outside the Inputs list" {
  local unwired=()
  local input hits

  while read -r input; do
    [[ -z "$input" ]] && continue
    # Count references outside the declaration line itself. pr_url is the
    # invocation argument and is referenced as <pr_url> / pr_number throughout.
    # Whole-word (-w): a substring count lets a longer sibling carry a shorter
    # input, e.g. delta_gate_min_candidates keeping `delta_gate` green.
    # docs/superpowers/ holds archived plans and specs; scripts/tests/ is test
    # fixtures. Neither is a reference the loop reads at runtime, and counting
    # the archived plans is what let `dry_run` look wired while branching nowhere.
    hits=$(
      {
        grep -cw "$input" "${REPO_ROOT}/SKILL.md" || true
        grep -rcw --exclude-dir=superpowers --exclude-dir=tests "$input" \
          "${REPO_ROOT}/docs" "${REPO_ROOT}/scripts" 2>/dev/null |
          awk -F: '{s+=$NF} END {print s+0}'
      } | awk '{s+=$1} END {print s+0}'
    )
    # 1 hit = the declaration line only.
    if [[ "$hits" -le 1 ]]; then
      unwired+=("$input")
    fi
  done < <(declared_inputs)

  if [[ ${#unwired[@]} -gt 0 ]]; then
    echo "Declared in SKILL.md '## Inputs' but referenced nowhere else:" >&2
    printf '  - %s\n' "${unwired[@]}" >&2
    echo "Wire the input, or remove the declaration." >&2
    return 1
  fi
}
