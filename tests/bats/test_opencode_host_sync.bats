#!/usr/bin/env bats

# opencode host-surface drift guard. The tier-agent names exist in three
# places: the mapping table in docs/model-overrides.md (what the orchestrator
# dispatches), the files under hosts/opencode/agent/ (what ships), and the
# OPENCODE_AGENTS array in install.sh (what gets linked). All three must agree.

load test_helper

doc_agents() {
  # Second cell of each two-column mapping-table row, prl-* only, so the
  # Claude alias rows and the inherit row (`general`) drop out.
  sed -nE 's/^\| `[^`]*` \| `([a-z0-9._-]+)` \|[[:space:]]*$/\1/p' \
    "${REPO_ROOT}/docs/model-overrides.md" | grep '^prl-' | sort
}

file_agents() {
  (cd "${REPO_ROOT}/hosts/opencode/agent" && ls prl-*.md | sed 's/\.md$//' | sort)
}

script_agents() {
  sed -nE 's/^OPENCODE_AGENTS=\(([^)]*)\)/\1/p' "${REPO_ROOT}/install.sh" |
    tr ' ' '\n' | sed 's/\.md$//' | grep . | sort
}

@test "every documented prl-* tier agent has a shipped agent file" {
  local documented
  documented="$(doc_agents)"
  [[ -n "$documented" ]] || {
    echo "no prl-* rows parsed from docs/model-overrides.md — table format changed?"
    return 1
  }
  [[ "$documented" == "$(file_agents)" ]]
}

@test "install.sh OPENCODE_AGENTS matches the shipped agent files" {
  [[ "$(script_agents)" == "$(file_agents)" ]]
}

@test "opencode agent files declare subagent mode" {
  local f
  for f in "${REPO_ROOT}"/hosts/opencode/agent/prl-*.md; do
    grep -q '^mode: subagent$' "$f" || {
      echo "missing 'mode: subagent' in $f"
      return 1
    }
  done
}
