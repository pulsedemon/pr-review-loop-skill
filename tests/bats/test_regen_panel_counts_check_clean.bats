#!/usr/bin/env bats

# Smoke gate for scripts/regen_panel_counts.py — the generator that owns
# panel-count phrases across SKILL.md, tests/scenarios/*.md, and
# reviewers/*.md. Replaces test_panel_count_phrase_sync.bats.
#
# Three checks: --check confirms no rendered phrase has drifted from
# its template; --validate-markers confirms every region's start/end
# markers are balanced and well-formed; --validate-coverage runs the
# corpus-wide closure scan that requires every numbered persona-count
# phrase to be wrapped in a region or matched by an allowlist pattern.

load test_helper

@test "regen_panel_counts.py --check passes on a clean tree" {
  python3 "${REPO_ROOT}/scripts/regen_panel_counts.py" --check
}

@test "every panel-count region in the corpus has a matching close marker" {
  python3 "${REPO_ROOT}/scripts/regen_panel_counts.py" --validate-markers
}

@test "every numbered persona-count phrase is wrapped or allowlisted" {
  python3 "${REPO_ROOT}/scripts/regen_panel_counts.py" --validate-coverage
}
