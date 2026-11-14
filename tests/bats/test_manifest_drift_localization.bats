#!/usr/bin/env bats

# Drift-localization contract: adding a fake entry to the manifest
# must produce one specific failure message per dependent surface so
# the operator knows where the conflict starts and where to fix it.
#
# Implementation: swap the real reviewers/personas.yaml with a
# fixture containing one extra persona ('phantom') that no other
# surface references, then run each dependent sync test and assert
# each names a specific surface in its failure output.

load test_helper

# Work against an isolated copy of the repo with the phantom fixture
# swapped in — never the real reviewers/personas.yaml. An earlier version
# overwrote the real manifest in setup() and restored it in teardown(),
# which raced the manifest-sync tests under `bats --jobs` (they would read
# personas.yaml mid-swap and see 'phantom'). $SKILL is a self-contained
# copy: the sub-test bats files resolve REPO_ROOT from their own path, and
# regen-check.sh resolves its root via `git rev-parse`, so the --git
# copy keeps both pointed inside the copy.
setup() {
  SKILL="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree --git "$SKILL"
  cp "${SKILL}/tests/fixtures/manifest_with_extra_persona.yaml" \
     "${SKILL}/reviewers/personas.yaml"
}

@test "filesystem-sync test fails and mentions phantom" {
  # the public entrypoint initializes functions lost across parallel workers.
  run "${BATS_ROOT}/bin/bats" -f "filesystem matches the manifest" \
    "${SKILL}/tests/bats/test_reviewer_enum_filesystem_sync.bats"
  [[ "$status" -ne 0 ]] || {
    echo "expected failure with phantom persona; got success"
    return 1
  }
  echo "$output" | grep -q "phantom" || {
    echo "expected output to mention 'phantom'; got:"
    echo "$output"
    return 1
  }
}

@test "Move C drift guard fails because phantom.md doesn't exist on disk" {
  # The Move C drift guard tries to extract the section from
  # reviewers/phantom.md (since phantom has move_c: true in the
  # fixture). The file doesn't exist, so extraction returns empty
  # and the 'section is present' precondition fires.
  run "${BATS_ROOT}/bin/bats" "${SKILL}/tests/bats/test_move_c_drift_guard.bats"
  [[ "$status" -ne 0 ]] || {
    echo "expected failure; got success"
    return 1
  }
  echo "$output" | grep -q "phantom.md" || {
    echo "expected output to mention 'phantom.md'; got:"
    echo "$output"
    return 1
  }
}

@test "scripts/regen-check.sh fails with exit 5 and surfaces phantom in the diff" {
  # When the manifest gains phantom, cog regenerates the SKILL.md
  # "Reviewer personas" section to include a phantom bullet — which
  # then diffs against the on-disk SKILL.md (which doesn't have one).
  # Likewise scripts/regen_schema_enum.py regenerates the enum to
  # include phantom and diffs against the on-disk schema. Either
  # failure exits non-zero with a unified diff containing the literal
  # 'phantom'.
  #
  # regen-check.sh resolves its root via `git rev-parse --show-toplevel`,
  # which follows cwd — not the script's own location. Run it with cwd
  # inside $SKILL so it checks the fixture manifest, not the real repo.
  run bash -c "cd '${SKILL}' && bash scripts/regen-check.sh"
  [[ "$status" -eq 5 ]] || {
    echo "expected scripts/regen-check.sh to fail with exit 5 (drift) given the fixture manifest;"
    echo "got status=$status. Output:"
    echo "$output"
    return 1
  }
  echo "$output" | grep -q "phantom" || {
    echo "expected scripts/regen-check.sh output to mention 'phantom' in the diff; got:"
    echo "$output"
    return 1
  }
}

@test "scripts/regen-check.sh failure message points at scripts/regen.sh" {
  # The cog --check-fail-msg and regen_schema_enum.py both must point
  # the operator at the one-command fix. This guards against a future
  # refactor that drops the hint or replaces it with a generic 'check
  # failed' diagnostic that hides where to recover.
  # cwd must be inside $SKILL — see the note in the exit-5 test above.
  run bash -c "cd '${SKILL}' && bash scripts/regen-check.sh"
  [[ "$status" -ne 0 ]] || return 1
  echo "$output" | grep -q "scripts/regen.sh" || {
    echo "expected output to recommend 'scripts/regen.sh'; got:"
    echo "$output"
    return 1
  }
}
