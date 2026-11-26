#!/usr/bin/env bats

load test_helper

# keep the real flags and addendums so phantom is the only drift.
setup() {
  SKILL="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree --git "$SKILL"
  python3 - "${SKILL}/reviewers/personas.yaml" <<'PY'
import sys
from pathlib import Path

import yaml

path = Path(sys.argv[1])
manifest = yaml.safe_load(path.read_text())
manifest["panel"].append({"name": "phantom", "description": "fixture stub", "move_c": True})
path.write_text(yaml.safe_dump(manifest, sort_keys=False))
PY
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
  # regen-check resolves its root from the current directory.
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
  run bash -c "cd '${SKILL}' && bash scripts/regen-check.sh"
  [[ "$status" -ne 0 ]] || return 1
  echo "$output" | grep -q "scripts/regen.sh" || {
    echo "expected output to recommend 'scripts/regen.sh'; got:"
    echo "$output"
    return 1
  }
}
