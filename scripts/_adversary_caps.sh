#!/usr/bin/env bash
# ADVERSARY_CAP for the §4d.0 adversary counters, written from
# manifests/adversary-caps.yaml by scripts/regen_adversary_caps.py.
# scripts/state_init.sh sources it and exits 6 when it disagrees with
# the schema maxima.
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
