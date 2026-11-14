#!/usr/bin/env bats

# Membership sync for the §4b procedure-move bullets.
#
# reviewers/personas.yaml is the source of truth for which panel personas
# carry Move A, Move A.1 and Move B; scripts/_move_c_bullet_for_cog.py
# renders the SKILL.md bullets from it. Nothing previously pinned that
# membership against the personas on disk, which is how SKILL.md came to
# omit blind_spots from Move A and blind_spots + error_handling from
# Move B (#124, #128).
#
# This test compares the manifest flags against the `## Procedure move`
# section headings actually present in reviewers/*.md. It is the guard
# that would have caught the original drift in either direction: a
# persona that gains a move section without a manifest flag, or a flag
# set for a persona carrying no such section.
#
# The adversary is excluded deliberately. It is not in personas.yaml
# `panel:` and carries one combined "Procedure moves A/A.1/B/C
# (inherited from the panel)" heading rather than per-move sections;
# SKILL.md states its inheritance in prose instead.
#
# Headings read `## Procedure move A —` (lowercase "move", em dash), so
# the scan is case-insensitive and anchored. A case-sensitive `grep -l
# 'Move A'` silently misses correctness.md and tests.md — the exact
# mistake that put a wrong persona list in #124's own reproduce command.

load test_helper

# Personas whose reviewers/<name>.md carries a real heading for the move.
disk_carriers() {
  local pattern="$1"
  grep -ril "^## Procedure move ${pattern}" "${REPO_ROOT}"/reviewers/*.md 2>/dev/null \
    | xargs -n1 basename \
    | sed 's/\.md$//' \
    | grep -v '^adversary$' \
    | sort
}

manifest_carriers() {
  python3 "${REPO_ROOT}/scripts/personas_manifest.py" --list "$1" | sort
}

assert_move_sync() {
  local pattern="$1" listing="$2" label="$3"
  local disk manifest
  disk=$(disk_carriers "${pattern}")
  manifest=$(manifest_carriers "${listing}")

  [ "${disk}" = "${manifest}" ] || {
    echo "${label} membership drift between personas.yaml and reviewers/*.md"
    echo "  on disk   : $(echo "${disk}" | tr '\n' ' ')"
    echo "  manifest  : $(echo "${manifest}" | tr '\n' ' ')"
    echo "Set the ${listing%-names} flag in reviewers/personas.yaml to match the"
    echo "sections on disk, then run scripts/regen.sh."
    return 1
  }
}

@test "Move A membership matches the persona files on disk" {
  assert_move_sync "A —" "move-a-names" "Move A"
}

@test "Move A.1 membership matches the persona files on disk" {
  assert_move_sync "A\\.1 —" "move-a1-names" "Move A.1"
}

@test "Move B membership matches the persona files on disk" {
  assert_move_sync "B —" "move-b-names" "Move B"
}

@test "Move C membership matches the persona files on disk" {
  assert_move_sync "C —" "move-c-names" "Move C"
}

@test "the rendered SKILL.md bullets name exactly the manifest personas" {
  local listing move_label line
  for pair in "move-a-names:Move A " "move-a1-names:Move A.1 " "move-b-names:Move B " "move-c-names:Move C "; do
    listing="${pair%%:*}"
    move_label="${pair##*:}"
    line=$(grep -F -e "- **${move_label}(" "${REPO_ROOT}/SKILL.md" || true)

    # render() omits a bullet entirely when no persona carries the move,
    # rather than emitting one with an empty list. Absence is the correct
    # output there, so require it rather than failing on the missing line.
    if [ -z "$(manifest_carriers "${listing}")" ]; then
      [ -z "${line}" ] || {
        echo "${move_label}has no manifest carriers but SKILL.md still shows a bullet"
        echo "  bullet: ${line}"
        return 1
      }
      continue
    fi

    [ -n "${line}" ] || {
      echo "no §4b bullet found for ${move_label}"
      return 1
    }

    # Every manifest persona is named in its bullet.
    while read -r name; do
      [ -z "${name}" ] && continue
      echo "${line}" | grep -qF "\`${name}\`" || {
        echo "${move_label}bullet omits \`${name}\` (set in personas.yaml)"
        echo "  bullet: ${line}"
        return 1
      }
    done < <(manifest_carriers "${listing}")

    # And the bullet names nothing else. Extracting the backticked
    # identifiers from the persona-list prefix (rather than iterating the
    # current panel) is what catches a stale name: one dropped from the
    # manifest is in neither list, so a panel-driven loop never visits it.
    local prefix expected rendered
    prefix="${line%%: *}"
    expected=$(manifest_carriers "${listing}")
    rendered=$(echo "${prefix}" | grep -oE '`[a-z][a-z0-9_]*`' | tr -d '`' | sort)

    [ "${rendered}" = "${expected}" ] || {
      echo "${move_label}bullet names a different persona set than personas.yaml"
      echo "  rendered : $(echo "${rendered}" | tr '\n' ' ')"
      echo "  manifest : $(echo "${expected}" | tr '\n' ' ')"
      echo "  bullet   : ${line}"
      return 1
    }
  done
}
