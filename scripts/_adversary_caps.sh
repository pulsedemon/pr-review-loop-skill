#!/usr/bin/env bash
# Canonical cap values for §4d.0 adversary counters.
#
# Source of truth: manifests/adversary-caps.yaml (`cap` field). The
# generator scripts/regen_adversary_caps.py writes that value into
# the schema (templates/state.schema.json maxima for both
# shallow_adversary_runs and shallow_approval_adversary_runs), this
# helper, and the cap sentence in docs/adversary.md.
# scripts/state_init.sh cross-checks helper vs schema at runtime
# (exit 6 on mismatch). The bats file
# tests/bats/test_adversary_cap_behavioral.bats covers behavioral
# regex fixtures and the SKILL.md dual-counter proximity canary
# (no longer the cap-literal pin — that's the generator's job).
#
# Guard against a caller preset (stale env from a test harness, accidental
# override) that disagrees with the contract value. `readonly` alone does
# NOT catch this — `readonly VAR=value` overwrites an existing non-readonly
# variable silently and only blocks *subsequent* reassignment. The explicit
# check below makes the intent enforceable.
# shellcheck disable=SC2034  # sourced by callers; consumed externally
# [[[cog: adversary_caps_sh ]]]
if [[ -n "${ADVERSARY_CAP:-}" && "${ADVERSARY_CAP}" != "2" ]]; then
  echo "ERROR: ADVERSARY_CAP is preset to '${ADVERSARY_CAP}', expected '2'." >&2
  echo "       Unset it before sourcing scripts/_adversary_caps.sh." >&2
  return 1 2>/dev/null || exit 1
fi
readonly ADVERSARY_CAP=2
# [[[end]]]
