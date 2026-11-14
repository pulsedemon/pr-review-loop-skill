#!/usr/bin/env bats

# Gated personas early-exit ABOVE their severity sections: the applicability
# gate returns verdict:approve with empty findings unless the diff adds a
# recognized surface (blind_spots additionally runs Move A and Move C past
# its gate; see reviewers/blind_spots.md '## Rules'). So a severity rule naming a surface the gate does not
# admit is dead on arrival — the persona exits above it and never reads the
# rule.
#
# The failure is silent in both directions. The persona returns a well-formed
# approve, indistinguishable from a genuine "nothing to flag here". No error,
# no shallow-review flag, no missing finding to notice. Recall just drops.
#
# The contract this pins: every severity bullet on a gated persona cites the
# gate surface id that admits it, or every id when it spans surfaces. That
# converts an intractable prose-matching
# problem into set membership. The convention comes from blind_spots.md, which
# already tags every severity bullet with (a)/(b1)/(b2)/(c).
#
# Not pinned here, but pinned elsewhere: blind_spots' early-exit polarity.
# It was left unpinned while that prose still conflicted with Move A and
# Move C, both of which raise blockers on surfaces outside (a)/(b)/(c).
# #121 resolved the conflict by carving both moves out of the gate, so the
# polarity now lives with the other gate-text pins in
# test_applicability_gate_text.bats rather than being duplicated here.
#
# Also out of scope by construction: move-based severity rules live outside
# the "## What to flag as" sections, so check 3 cannot see them.

load test_helper

# Gated personas and where their surface ids come from. This is a test-local
# list, not a personas.yaml key: gatedness is not a manifest fact, and two
# entries do not justify a schema change.
#
# The id sources genuinely differ. yagni numbers the bullets under its
# "## Applicability gate" heading; blind_spots has NO such heading at all —
# its ids are "### (x)" headings under "## Categories you cover". An
# extractor keyed to one shape yields zero ids for the other, which would
# make checks 3 and 4 vacuous for that persona.
GATED_PERSONAS=(yagni blind_spots)

_gate_ids() {
  local persona="$1" file="${REPO_ROOT}/reviewers/$1.md"
  case "$persona" in
    yagni)
      awk '/^## Applicability gate/{c=1;next} c&&/^## /{c=0} c&&/^- /' "$file" |
        grep -oE '^- \(([a-z][a-z0-9]?)\)' | grep -oE '[a-z][a-z0-9]?'
      ;;
    blind_spots)
      awk '/^## Categories you cover/{c=1;next} c&&/^## /{c=0} c&&/^### /' "$file" |
        grep -oE '^### \(([a-z][a-z0-9]?)\)' | grep -oE '\([a-z][a-z0-9]?\)' | tr -d '()'
      ;;
    *)
      echo "unknown gated persona: $persona" >&2
      return 1
      ;;
  esac
}

# Every "- " bullet under every "## What to flag as ..." heading. Re-arms at
# each such heading so blocker AND suggestion sections are both collected.
_severity_bullets() {
  awk '/^## What to flag as/{c=1;next} c&&/^## /{c=0} c&&/^- /' \
    "${REPO_ROOT}/reviewers/$1.md"
}

# Claimed tags in one bullet: every parenthesized 1-2 char lowercase token.
#
# Match by SHAPE, then validate against the live id set in the caller. Do not
# filter to live ids here: that makes the dead-id check vacuous, because a
# bullet tagged (z) would have its only tag discarded and read as "untagged"
# instead of "cites a dead id".
#
# The shape constraint is what keeps prose out — "(logging, validation)",
# "(or equivalent)", "(the premature-optimization suggestion path below)" all
# yield nothing. Known limit: an (a)-style ENUMERATION inside a severity
# bullet would read as a tag. That style exists in yagni.md but in no severity
# bullet today; if this test ever fires on a rule you believe is correct,
# check for a shape collision before adding a gate surface.
_bullet_tags() {
  grep -oE '\([a-z][a-z0-9]?\)' <<<"$1" | tr -d '()' | sort -u
}

@test "gate reachability: the gated-persona list is non-empty and every file exists" {
  # A loop over an empty list passes for the wrong reason. Every check below
  # iterates GATED_PERSONAS, so this guards all of them.
  [[ "${#GATED_PERSONAS[@]}" -ge 1 ]] || {
    echo "GATED_PERSONAS is empty; every check in this file is vacuous"
    return 1
  }
  local p
  for p in "${GATED_PERSONAS[@]}"; do
    [[ -f "${REPO_ROOT}/reviewers/${p}.md" ]] || {
      echo "reviewers/${p}.md is listed in GATED_PERSONAS but does not exist"
      return 1
    }
  done
}

@test "gate reachability: every gated persona's gate yields at least one surface id" {
  # A gate whose ids stop parsing (heading renamed, numbering dropped) would
  # make the tag checks below trivially pass: an empty live-id set turns
  # "cites a live id" into "cites nothing", and every bullet would fail
  # loudly instead — or, worse, a loosened check would pass silently.
  local p count
  for p in "${GATED_PERSONAS[@]}"; do
    count=$(_gate_ids "$p" | wc -l | tr -d ' ')
    [[ "$count" -ge 1 ]] || {
      echo "no gate surface ids parsed for reviewers/${p}.md"
      echo "  yagni: '- (x) ' bullets under '## Applicability gate'"
      echo "  blind_spots: '### (x)' headings under '## Categories you cover'"
      echo "(the id source differs per persona; see _gate_ids in this file)"
      return 1
    }
  done
}

@test "gate reachability: every severity bullet cites a gate surface" {
  local p bullet tags count
  for p in "${GATED_PERSONAS[@]}"; do
    count=$(_severity_bullets "$p" | wc -l | tr -d ' ')
    [[ "$count" -ge 1 ]] || {
      echo "no severity bullets found in reviewers/${p}.md"
      echo "(expected '- ' bullets under a '## What to flag as ...' heading;"
      echo " if the headings changed, this check is silently covering nothing)"
      return 1
    }
    while IFS= read -r bullet; do
      [[ -n "$bullet" ]] || continue
      tags=$(_bullet_tags "$bullet")
      [[ -n "$tags" ]] || {
        echo "untagged severity bullet in reviewers/${p}.md:"
        echo "    ${bullet:0:100}"
        echo ""
        echo "Every severity rule on a gated persona must cite the gate surface"
        echo "id that admits it, or the rule is unreachable: the gate exits above"
        echo "it and the persona never reads it. Add the id, e.g. '- (c) ...'."
        echo "if no gate surface admits this rule, it is unreachable."
        echo "verify the intended applicability before adding a surface; see"
        echo "docs/editing-personas.md."
        return 1
      }
    done < <(_severity_bullets "$p")
  done
}

@test "gate reachability: every cited tag names a live gate surface" {
  # Catches a rule tagged against a surface that was later renamed or removed.
  # Distinct from the check above: that one fires on NO tag, this one on a tag
  # that exists but points nowhere.
  local p bullet tag live
  for p in "${GATED_PERSONAS[@]}"; do
    live=$(_gate_ids "$p")
    while IFS= read -r bullet; do
      [[ -n "$bullet" ]] || continue
      while IFS= read -r tag; do
        [[ -n "$tag" ]] || continue
        # Accept a sub-id: blind_spots splits (b) into b1/b2 in prose and its
        # bullets cite the sub-ids, never bare b. Without this, b1 reads as
        # dead and this check fires on correct rules.
        grep -qxF "$tag" <<<"$live" ||
          grep -qxF "${tag%[0-9]}" <<<"$live" || {
            echo "severity bullet in reviewers/${p}.md cites gate surface ($tag),"
            echo "which is not a live surface id."
            echo "    ${bullet:0:100}"
            echo "  live ids: $(tr '\n' ' ' <<<"$live")"
            echo ""
            echo "Either the surface was renamed/removed and the rule is now"
            echo "unreachable, or the tag is a typo."
            return 1
          }
      done < <(_bullet_tags "$bullet")
    done < <(_severity_bullets "$p")
  done
}

@test "gate reachability: type_design restates its gate inside the blocker section" {
  # type_design is deliberately NOT tagged: its gate is a single condition
  # ("at least one type definition") whose bullets are language syntaxes, not
  # distinct surfaces, so any type rule is admitted by construction and there
  # is nothing for a tag to disambiguate. What keeps it honest instead is the
  # explicit back-reference in its blocker preconditions. Pin that.
  grep -qF 'The PR adds or modifies a type definition (per the applicability gate)' \
    "${REPO_ROOT}/reviewers/type_design.md" || {
    echo "type_design.md blocker section no longer restates the applicability gate"
    echo "(it is exempt from surface tagging because its gate is one condition,"
    echo " not an enumerated surface list; this back-reference is what ties its"
    echo " severity rules to the gate instead.)"
    return 1
  }
}
