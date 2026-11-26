#!/usr/bin/env bats

load test_helper

# keep the real flags and addendums so phantom is the only drift.
setup() {
  export LC_ALL=C PYTHONUTF8=0 PYTHONCOERCECLOCALE=0
  SKILL="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree --git "$SKILL"
  python3 - "${SKILL}/reviewers/personas.yaml" <<'PY'
import sys
from pathlib import Path

import yaml

path = Path(sys.argv[1])
manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
manifest["panel"].append({"name": "phantom", "description": "fixture stub", "move_c": True})
path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
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
  # regen-check resolves its root from the current git checkout.
  run bash -c "cd '${SKILL}' && bash scripts/regen-check.sh"
  [[ "$status" -eq 5 ]] || {
    echo "expected scripts/regen-check.sh to fail with exit 5 (drift) after adding phantom"
    echo "got status=$status. Output:"
    echo "$output"
    return 1
  }
  printf '%s\n' "$output" >"$BATS_TEST_TMPDIR/regen.log"
  python3 - "$REPO_ROOT/reviewers/personas.yaml" "$SKILL/reviewers/personas.yaml" "$BATS_TEST_TMPDIR/regen.log" <<'PY'
import re
import sys
from pathlib import Path

import yaml

original, mutated = (yaml.safe_load(Path(path).read_text(encoding="utf-8")) for path in sys.argv[1:3])
phantom = mutated["panel"].pop()
if phantom != {"name": "phantom", "description": "fixture stub", "move_c": True} or mutated != original:
    raise SystemExit("expected the manifest to differ only by the appended phantom persona")

lines = Path(sys.argv[3]).read_text(encoding="utf-8").splitlines()
lines.remove("--- current SKILL.md")
lines.remove("+++ changed SKILL.md")
added = [line[1:] for line in lines if line.startswith("+")]
removed = [line[1:] for line in lines if line.startswith("-")]
added.remove("- `phantom.md`: fixture stub")
prefix = "- **Move C (cross-doc consistency)**, "
if len(removed) != 1 or not removed[0].startswith(prefix):
    raise SystemExit(f"expected one removed Move C bullet, got {removed!r}")
heading, body = removed[0][len(prefix):].split(": ", 1)
names = re.findall(r"`([^`]+)`", heading)
carriers = ", ".join(f"`{name}`" for name in sorted([*names, "phantom"]))
if added != [f"{prefix}{carriers}: {body}"]:
    raise SystemExit(f"expected only phantom added to the Move C carriers, got {added!r}")
PY
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
