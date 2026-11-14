#!/usr/bin/env bats

# Parallel fan-out cross-surface drift guard. Pins the load-bearing invariants:
#   1. reviewer and delta-gate fan-out phases launch in the same batched
#      parallel spawn/call/message when the host supports parallel spawning;
#   2. a phase is batched when all of its launches share one message and
#      results are awaited only after the last launch;
#   3. sequential fallback is allowed only when that capability is unavailable;
#   4. outputs stay independent until synthesis (reviewers) or
#      validation/selection (delta-gate).
#
# The SKILL.md half is asserted per section, because a whole-file pattern can
# be satisfied by either §4a.1 or §4b alone.
#
# Mutation-tested before requesting review:
#   - delete §4a.1's batching sentence -> §4a.1 test fails, §4b test stays
#     green.
#   - delete §4b's batching clause -> §4b test fails, §4a.1 stays green.
#   - rename the `#### 4a.1.` heading -> §4a.1 test fails on the extraction
#     anchor rather than passing vacuously.
#   - move §4a.1's batching clause up into §4a -> §4a.1 test still fails.
#   - rename `#### 4a.1.` to `#### 4a.1.1.` -> §4a.1 test fails.
#   - drop §4a.1's "Validate each ... then pass the trusted results" sequence
#     -> §4a.1 test fails. invariant 4 above is per-phase: §4b pins it with
#     "independent until synthesis", and this is the delta-gate half. without
#     it the gate could feed unvalidated results straight into selection.
#   - replace the recipe sentence with the old "non-compliant" prohibition ->
#     every surface's test fails.

load test_helper

assert_required_patterns() {
  local path="$1"
  shift

  run python3 - <<'PY' "$path" "$@"
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
args = sys.argv[2:]

if len(args) % 2:
    raise SystemExit("expected pattern/message pairs")

text = path.read_text()
for pattern, message in zip(args[::2], args[1::2]):
    if not re.search(pattern, text, re.IGNORECASE | re.DOTALL):
        raise SystemExit(message)
PY
  [ "$status" -eq 0 ]
}

# Extract one SKILL.md section by its `#### <id>.` heading, stopping at the
# next `####`. §4a.1 and §4b carry near-identical batching sentences, so a
# whole-file grep cannot tell which one it matched: an alternation like
# `(that phase|a reviewer phase)` is satisfied by either section alone.
#
# The heading is matched as `#### <id>. ` including the trailing space, which
# makes the id exact in both directions:
#   - `4a` must not open at `#### 4a.` and then swallow §4a.1, which would let
#     wording sitting in §4a satisfy §4a.1's pins;
#   - `4a.1` must not open at `#### 4a.1.1.`, which would keep the liveness
#     check below green after §4a.1 was renamed out from under it.
# A nested id has a digit where the separator space belongs, so it fails.
_skill_section() {
  awk -v want="#### $1. " '
    substr($0, 1, length(want)) == want { capturing = 1; print; next }
    capturing && /^#### / { capturing = 0 }
    capturing { print }
  ' "${REPO_ROOT}/SKILL.md"
}

# Same contract as assert_required_patterns, against a text blob instead of a
# file, so a single section can be asserted in isolation.
assert_section_patterns() {
  local body="$1"
  local label="$2"
  shift 2

  # SKILL.md headings have no `§`; strip it so the message names the anchor the
  # extractor actually looks for.
  [[ -n "$body" ]] || {
    echo "could not extract ${label} from SKILL.md"
    echo "  the '#### ${label#§}.' heading anchor no longer matches. the batching"
    echo "    pins below are unverifiable until the anchor is realigned"
    return 1
  }

  run python3 -c '
import re
import sys

label = sys.argv[1]
args = sys.argv[2:]
text = sys.stdin.read()

if len(args) % 2:
    raise SystemExit("expected pattern/message pairs")

for pattern, message in zip(args[::2], args[1::2]):
    if not re.search(pattern, text, re.IGNORECASE | re.DOTALL):
        raise SystemExit(f"{label}: {message}")
' "$label" "$@" <<<"$body"
  [ "$status" -eq 0 ]
}

@test "SKILL.md §4a.1 pins the batched delta-gate fan-out contract" {
  assert_section_patterns "$(_skill_section '4a.1')" "§4a.1" \
    "one subagent call per candidate persona, all inside a single message" \
    "missing batched fan-out recipe" \
    "await results only after the last launch" \
    "missing await-after-last-launch rule" \
    "When the host cannot spawn subagents in parallel, launch sequentially" \
    "missing sequential-fallback guard" \
    "keep the gate outputs independent until validation/selection" \
    "missing gate-output independence rule" \
    "Validate each with .*?validate_gate_output.*?then pass the trusted results" \
    "missing gate-output validate-before-select ordering"
}

@test "SKILL.md §4b pins the batched reviewer fan-out contract" {
  assert_section_patterns "$(_skill_section '4b')" "§4b" \
    "one subagent call per persona in .panel_selection\\.ran., all inside a single message" \
    "missing batched fan-out recipe" \
    "await results only after the last launch" \
    "missing await-after-last-launch rule" \
    "When the host cannot spawn subagents in parallel, launch sequentially" \
    "missing sequential-fallback guard" \
    "keep those outputs independent until synthesis" \
    "missing reviewer-output independence rule" \
    "Stop waiting on the panel at the \\[reviewer budget\\]\\(docs/reviewer-orchestration\\.md#reviewer-budget\\)" \
    "missing reviewer-budget pointer"
}

@test "AGENTS.md mirrors the batched fan-out contract for both fan-outs" {
  assert_required_patterns "${REPO_ROOT}/AGENTS.md" \
    "one subagent call per reviewer or gate candidate, all inside a single\\s+message" \
    "missing batched launch recipe" \
    "await results only after the last launch" \
    "missing await-after-last-launch rule" \
    "When the host cannot\\s+spawn subagents in parallel, either fan-out may run sequentially" \
    "missing conditional sequential fallback" \
    "independent.*?synthesis \\(reviewers\\) or\\s+validation/selection \\(delta-gate\\)" \
    "missing independence rule for sequential fallback"
}

@test "docs/delta-gate.md pins batched gate fan-out and isolated fallback" {
  assert_required_patterns "${REPO_ROOT}/docs/delta-gate.md" \
    "one subagent call per candidate, all inside a single\\s+message" \
    "missing batched gate launch recipe" \
    "await results only after the last\\s+launch" \
    "missing await-after-last-launch rule" \
    "When the host cannot spawn subagents in parallel, the gate launches\\s+run sequentially" \
    "missing gate sequential-fallback guard" \
    "keep outputs independent until validation/selection" \
    "missing gate-output independence rule"
}

@test "README summarizes batched reviewer and delta-gate fan-out behavior" {
  assert_required_patterns "${REPO_ROOT}/README.md" \
    "one subagent call per reviewer, all inside a single message" \
    "missing reviewer batched-launch summary" \
    "await results only after the last launch" \
    "missing await-after-last-launch summary" \
    "delta-gate candidate fan-out follows the same recipe" \
    "missing delta-gate recipe summary" \
    "when the host cannot spawn subagents in parallel, either fan-out may run sequentially" \
    "missing conditional sequential fallback for both fan-outs" \
    "keep outputs independent until synthesis \\(reviewers\\) or validation/selection \\(delta-gate\\)" \
    "missing reviewer and delta-gate output independence summary"
}
