#!/usr/bin/env bats

load test_helper

validate() {
  echo "$1" | python3 "${SCRIPTS}/validate_gate_output.py"
}

@test "well-formed relevant=true output passes" {
  run validate '{"reviewer":"security","relevant":true,"reason":"new auth code"}'
  [ "$status" -eq 0 ]
}

@test "well-formed relevant=false output passes" {
  run validate '{"reviewer":"performance","relevant":false,"reason":"docs-only delta"}'
  [ "$status" -eq 0 ]
}

@test "missing gate schema exits 2 with schema-load error" {
  copy_skill_tree
  rm "${BATS_TEST_TMPDIR}/skill/reviewers/gate.schema.json"
  run bash -c "echo '{\"reviewer\":\"security\",\"relevant\":true,\"reason\":\"x\"}' | python3 ${BATS_TEST_TMPDIR}/skill/scripts/validate_gate_output.py"
  [ "$status" -eq 2 ]
  [[ "$output" == *"cannot load schema"* ]]
}

@test "malformed gate schema exits 2 with schema-malformed error" {
  copy_skill_tree
  python3 - <<PY
import json
from pathlib import Path
p = Path("${BATS_TEST_TMPDIR}/skill/reviewers/gate.schema.json")
p.write_text(json.dumps({"type": "object", "properties": 1}))
PY
  run bash -c "echo '{\"reviewer\":\"security\",\"relevant\":true,\"reason\":\"x\"}' | python3 ${BATS_TEST_TMPDIR}/skill/scripts/validate_gate_output.py"
  [ "$status" -eq 2 ]
  [[ "$output" == *"schema is malformed"* ]]
}

@test "unknown reviewer name fails" {
  run validate '{"reviewer":"adversary","relevant":true,"reason":"x"}'
  [ "$status" -eq 2 ]
}

@test "missing relevant field fails" {
  run validate '{"reviewer":"tests","reason":"x"}'
  [ "$status" -eq 2 ]
}

@test "empty reason fails" {
  run validate '{"reviewer":"tests","relevant":true,"reason":""}'
  [ "$status" -eq 2 ]
}

@test "non-boolean relevant fails" {
  run validate '{"reviewer":"tests","relevant":"yes","reason":"x"}'
  [ "$status" -eq 2 ]
}

@test "extra property fails (additionalProperties false)" {
  run validate '{"reviewer":"tests","relevant":true,"reason":"x","extra":1}'
  [ "$status" -eq 2 ]
}

@test "non-JSON stdin fails" {
  run validate 'not json'
  [ "$status" -eq 2 ]
}

@test "missing reviewer field fails" {
  run validate '{"relevant":true,"reason":"x"}'
  [ "$status" -eq 2 ]
}
