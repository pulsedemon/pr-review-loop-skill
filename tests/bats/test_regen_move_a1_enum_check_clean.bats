#!/usr/bin/env bats

# Smoke test: scripts/regen_move_a1_enum.py --check passes on a clean
# tree, and the manifests/move-a1-enum.yaml manifest exists with exactly
# five values. The unit-test pytest suite covers all the drift cases —
# this file exists to fail loudly in CI if the in-tree mirror surfaces
# drift from the manifest.

load test_helper

@test "regen_move_a1_enum.py --check passes on a clean tree" {
  python3 "${REPO_ROOT}/scripts/regen_move_a1_enum.py" --check
}

@test "manifests/move-a1-enum.yaml exists and lists exactly five values" {
  local count
  count=$(python3 -c '
import sys, yaml
m = yaml.safe_load(open(sys.argv[1]).read())
print(len(m["move_a1_pattern"]))
' "${REPO_ROOT}/manifests/move-a1-enum.yaml")
  [[ "$count" == "5" ]] || {
    echo "expected 5 enum values, got $count"
    return 1
  }
}
