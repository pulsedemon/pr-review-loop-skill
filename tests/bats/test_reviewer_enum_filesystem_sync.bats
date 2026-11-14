#!/usr/bin/env bats

# The reviewer enum in reviewers/output.schema.json, the set of persona
# files in reviewers/, and reviewers/personas.yaml (the manifest) must all
# agree. Drift in any direction silently rejects persona outputs at
# validate_reviewer_output.py — the persona is non-functional with no
# panel-level signal.
#
# This test enforces transitive agreement: if manifest == enum and
# manifest == filesystem, then enum == filesystem. The manifest at
# reviewers/personas.yaml is the canonical intermediate; the bats
# failure messages name it as the fix location so the operator knows
# where the conflict starts.

load test_helper

# Note: the previous "reviewer enum matches the manifest" test was deleted
# when the enum became generator-managed by scripts/regen_schema_enum.py;
# `scripts/regen-check.sh` (invoked by
# test_persona_surfaces_generator_check.bats) is now the canonical
# enum-vs-manifest gate. We keep the filesystem-sync test below because
# the generator does NOT manage the on-disk persona files — adding or
# removing reviewers/<name>.md is still a deliberate human action.

@test "reviewers/*.md filesystem matches the manifest (panel + adversary + addendums)" {
  local fs_set
  fs_set=$(cd "${REPO_ROOT}/reviewers" && ls *.md | sort | tr '\n' ',')

  local manifest_files
  manifest_files=$(python3 "${SCRIPTS}/personas_manifest.py" --list all-known-files | sort | tr '\n' ',')

  if [[ "$fs_set" != "$manifest_files" ]]; then
    echo "reviewers/*.md / manifest mismatch — fix reviewers/personas.yaml or reviewers/:"
    echo "  filesystem (reviewers/*.md):       $fs_set"
    echo "  manifest panel+adversary+addendums: $manifest_files"
    echo ""
    echo "If you added a new persona file: add it to reviewers/personas.yaml panel."
    echo "If you added a shared addendum:   add it to reviewers/personas.yaml addendums."
    echo ""
    echo "Diff (filesystem vs manifest):"
    diff <(echo "$fs_set" | tr ',' '\n') <(echo "$manifest_files" | tr ',' '\n') || true
    return 1
  fi
}

@test "manifest-mismatch failure message names reviewers/personas.yaml" {
  # Round-8 review identified the previous single-string addendum allowlist
  # as a silent-break risk. The fix is the manifest, but the failure
  # message itself is now a contract — assert it points operators at
  # personas.yaml so a future test refactor can't regress to a generic
  # "set mismatch" message that hides where the canonical source lives.
  #
  # We assert the format exists in the test source (not by triggering a
  # failure) because the current state is in sync.
  grep -q "fix reviewers/personas.yaml" \
    "${REPO_ROOT}/tests/bats/test_reviewer_enum_filesystem_sync.bats" || {
    echo "test source missing the 'fix reviewers/personas.yaml' diagnostic"
    return 1
  }
}
