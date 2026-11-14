#!/usr/bin/env bats

# Shared addendums in reviewers/ are read by personas but are not personas
# themselves. The mechanism is a convention, not a generator: the file is
# declared in reviewers/personas.yaml under `addendums:`, and each reviewer
# file links it from its own H2 section. Nothing concatenates anything, so a
# persona that drops its link silently stops honoring the addendum with no
# panel-level signal.
#
# test_reviewer_enum_filesystem_sync.bats already pins the file set against
# the manifest. It does NOT pin the per-persona links, which is the half that
# actually delivers the rules to the reviewer. This file pins those.
#
# Two addendums are covered:
#
#   _working_tree_addendum.md   — every panel persona AND the adversary. The
#     adversary is not in `panel:`, so a panel-driven loop misses it; it gets
#     its own @test, mirroring how test_move_c_drift_guard.bats handles Move C
#     inheritance.
#   _human_comments_addendum.md — panel personas only. The adversary is
#     deliberately excluded (it receives no human_comments; SKILL.md §4b), and
#     that exclusion is asserted rather than assumed.

load test_helper

WORKING_TREE_ADDENDUM="_working_tree_addendum.md"
HUMAN_COMMENTS_ADDENDUM="_human_comments_addendum.md"

# Maximum non-blank line count for a persona's "## Working tree" section.
# The stub is the heading plus a one-line pointer. The cap exists because a
# preserved link does not stop someone re-inlining the canonical body: the
# canonical addendum is well over that, so any real re-inline trips this
# even when the link survives. Raise it with a comment explaining why, never
# silently.
PERSONA_WORKING_TREE_MAX_LINES=5

_panel_files() {
  local f
  while read -r f; do
    printf '%s\n' "${REPO_ROOT}/reviewers/${f}"
  done < <(python3 "${SCRIPTS}/personas_manifest.py" --list panel-files)
}

# Extract an H2 section by exact heading, ending at the next "## " heading.
_extract_section() {
  local file="$1" heading="$2"
  awk -v h="$heading" '
    $0 == h { capturing = 1; print; next }
    capturing && /^## / { capturing = 0 }
    capturing { print }
  ' "$file"
}

# Resolve the first markdown link target in $section whose path ends in
# $basename, relative to $file's directory, and echo the absolute path.
# Echoes nothing when the section carries no such link.
_resolve_link() {
  local file="$1" section="$2" base="$3"
  local link_path persona_dir resolved base_re
  # Escape ERE metacharacters in the basename before interpolating it. An
  # unescaped `.` matches any character, so `_working_tree_addendum.md` would
  # also match a link to `_working_tree_addendumXmd`. The disk-resolution
  # check below rejects that, but the pattern should not depend on a later
  # assertion to be correct. Matches the escaped-literal form used in
  # test_move_c_drift_guard.bats.
  base_re=$(printf '%s' "$base" | sed 's/[.[\*^$()+?{|]/\\&/g')
  link_path=$(echo "$section" \
    | grep -oE "\([^)]*${base_re}[^)]*\)" \
    | head -1 \
    | sed -E 's/^\(//; s/\)$//; s/#.*$//')
  [[ -n "$link_path" ]] || return 0
  persona_dir=$(dirname "$file")
  if [[ "$link_path" = /* ]]; then
    resolved="$link_path"
  else
    resolved=$(cd "$persona_dir" && cd "$(dirname "$link_path")" 2>/dev/null && pwd)/$(basename "$link_path")
  fi
  printf '%s\n' "$resolved"
}

@test "addendums: manifest reports at least 1 panel file (link checks are non-vacuous)" {
  # A loop over an empty list passes for the wrong reason. Every per-persona
  # assertion below iterates the manifest, so this guards all of them.
  local count
  count=$(python3 "${SCRIPTS}/personas_manifest.py" --list panel-files | wc -l | tr -d ' ')
  [[ "$count" -ge 1 ]] || {
    echo "manifest reports $count panel files; the link checks below have"
    echo "nothing to assert against. Fix reviewers/personas.yaml."
    return 1
  }
}

@test "addendums: both shared addendums are declared in the manifest and exist on disk" {
  local declared
  declared=$(python3 "${SCRIPTS}/personas_manifest.py" --list addendums)

  local a
  for a in "$WORKING_TREE_ADDENDUM" "$HUMAN_COMMENTS_ADDENDUM"; do
    grep -qxF "$a" <<<"$declared" || {
      echo "$a is not declared in reviewers/personas.yaml addendums:"
      echo "manifest addendums: $declared"
      echo ""
      echo "Fix reviewers/personas.yaml — an undeclared addendum also fails"
      echo "test_reviewer_enum_filesystem_sync.bats."
      return 1
    }
    [[ -f "${REPO_ROOT}/reviewers/${a}" ]] || {
      echo "$a is declared in reviewers/personas.yaml but missing from reviewers/"
      return 1
    }
  done
}

@test "addendums: every panel persona links the working-tree addendum, resolved on disk" {
  local files=()
  while IFS= read -r line; do files+=("$line"); done < <(_panel_files)

  local f section resolved expected
  expected="${REPO_ROOT}/reviewers/${WORKING_TREE_ADDENDUM}"
  for f in "${files[@]}"; do
    section=$(_extract_section "$f" "## Working tree")
    [[ -n "$section" ]] || {
      echo "'## Working tree' section missing in $f"
      echo "(every panel persona in reviewers/personas.yaml must carry the"
      echo " section linking ${WORKING_TREE_ADDENDUM}; without it the reviewer"
      echo " never reads the no-mutation rules and can revert the"
      echo " orchestrator's in-progress edit.)"
      return 1
    }
    resolved=$(_resolve_link "$f" "$section" "$WORKING_TREE_ADDENDUM")
    [[ -n "$resolved" ]] || {
      echo "'## Working tree' section in $f does not link ${WORKING_TREE_ADDENDUM}"
      echo "section body:"
      echo "$section" | sed 's/^/    /'
      return 1
    }
    [[ -f "$resolved" ]] || {
      echo "working-tree link in $f resolves to '$resolved', which is not a file"
      return 1
    }
    [[ "$resolved" = "$expected" ]] || {
      echo "working-tree link in $f resolves to '$resolved', not '$expected'"
      return 1
    }
  done
}

@test "addendums: the adversary links the working-tree addendum too" {
  # adversary.md is not in personas.yaml `panel:`, so the panel-driven test
  # above does not cover it. It runs in §4d.0, later in the iteration than the
  # panel and therefore closest in time to the §4e edit phase, which makes it
  # the highest-risk reviewer for clobbering work in progress.
  local f section resolved expected
  f="${REPO_ROOT}/reviewers/adversary.md"
  expected="${REPO_ROOT}/reviewers/${WORKING_TREE_ADDENDUM}"

  section=$(_extract_section "$f" "## Working tree")
  [[ -n "$section" ]] || {
    echo "'## Working tree' section missing in reviewers/adversary.md"
    echo "(the adversary is not in personas.yaml panel:, so the panel test"
    echo " above cannot catch this. It shares the same checkout and needs"
    echo " the same rules.)"
    return 1
  }
  resolved=$(_resolve_link "$f" "$section" "$WORKING_TREE_ADDENDUM")
  [[ "$resolved" = "$expected" ]] || {
    echo "adversary working-tree link resolves to '$resolved', not '$expected'"
    return 1
  }
}

@test "addendums: every panel persona links the human-comments addendum, resolved on disk" {
  local files=()
  while IFS= read -r line; do files+=("$line"); done < <(_panel_files)

  local f section resolved expected
  expected="${REPO_ROOT}/reviewers/${HUMAN_COMMENTS_ADDENDUM}"
  for f in "${files[@]}"; do
    section=$(_extract_section "$f" "## Human comments addendum")
    [[ -n "$section" ]] || {
      echo "'## Human comments addendum' section missing in $f"
      return 1
    }
    resolved=$(_resolve_link "$f" "$section" "$HUMAN_COMMENTS_ADDENDUM")
    [[ "$resolved" = "$expected" ]] || {
      echo "human-comments link in $f resolves to '$resolved', not '$expected'"
      return 1
    }
  done
}

@test "addendums: the adversary does NOT link the human-comments addendum" {
  # Deliberate asymmetry, not an oversight: the adversary receives no
  # human_comments block (SKILL.md §4b, docs/adversary.md). Asserting the
  # absence keeps a future "add the missing link everywhere" sweep from
  # quietly handing it context the design withholds.
  local f
  f="${REPO_ROOT}/reviewers/adversary.md"
  ! grep -qF "$HUMAN_COMMENTS_ADDENDUM" "$f" || {
    echo "reviewers/adversary.md links ${HUMAN_COMMENTS_ADDENDUM}, but the"
    echo "adversary is intentionally not given human_comments (SKILL.md §4b)."
    return 1
  }
}

@test "addendums: working-tree addendum keeps its prohibition and permission canaries" {
  local canonical="${REPO_ROOT}/reviewers/${WORKING_TREE_ADDENDUM}"
  local phrase

  # Every destructive command the addendum prohibits. `git checkout --` is the
  # one that actually destroyed an in-progress edit; the rest are the same
  # hazard by another name. Losing any one of them from the prose guts the
  # rule while every link above still passes.
  for phrase in 'git checkout' 'git stash' 'git restore' 'git reset' 'git clean'; do
    grep -qF "$phrase" "$canonical" || {
      echo "working-tree addendum no longer names '$phrase'"
      echo "(the prohibition list is the whole point of the file; a rewrite"
      echo " that drops one of these leaves the link intact and the rule gone.)"
      return 1
    }
  done

  # a copy lets reviewers test mutations without changing the shared checkout.
  grep -qF 'on a copy' "$canonical" || {
    echo "working-tree addendum no longer permits mutation testing 'on a copy'"
    echo "reviewers need a separate copy for mutation checks"
    return 1
  }
}

@test "addendums: working-tree addendum keeps the no-write and re-verify rules" {
  local canonical="${REPO_ROOT}/reviewers/${WORKING_TREE_ADDENDUM}"

  # The destructive-git list is only half the contract. These two rules cover
  # the other half, and neither shares a phrase with that list, so the canaries
  # above pass with either one deleted outright.

  # No writes to the checkout. This is what stops a reviewer leaving a mutation
  # behind, tracked or untracked; an untracked leftover trips the Step 3.6
  # porcelain guard on the next resume just as an edit does.
  grep -qF 'Do not modify anything inside this checkout' "$canonical" || {
    echo "working-tree addendum no longer carries the no-write rule"
    echo "(without it a reviewer may leave a mutation behind, which is one of"
    echo " the two failure modes this addendum exists to prevent.)"
    return 1
  }

  # Re-verify against the supplied SHA when the tree is dirty. This is what
  # stops a finding raised against uncommitted bytes that are not part of the
  # PR at all.
  grep -qF 'every modified file the finding rests on' "$canonical" || {
    echo "working-tree addendum no longer tells reviewers to re-verify every"
    echo "modified file a finding rests on"
    echo "(this is the rule that keeps a finding from being raised against"
    echo " uncommitted bytes. do not pin it on 'git show <head_sha>:<path>' —"
    echo " that string also appears in the mutation-testing block above, so"
    echo " the canary would pass with this paragraph deleted.)"
    return 1
  }
  grep -qF 'Uncommitted bytes are not this PR' "$canonical" || {
    echo "working-tree addendum lost the 'uncommitted bytes are not this PR' rule"
    return 1
  }
}

@test "addendums: each persona's Working tree section stays at or below the size cap" {
  local files=()
  while IFS= read -r line; do files+=("$line"); done < <(_panel_files)
  files+=("${REPO_ROOT}/reviewers/adversary.md")

  local f section nonblank
  for f in "${files[@]}"; do
    section=$(_extract_section "$f" "## Working tree")
    [[ -n "$section" ]] || continue  # missing-section case is covered above
    nonblank=$(echo "$section" | grep -cE '\S' || true)
    [[ "$nonblank" -le "$PERSONA_WORKING_TREE_MAX_LINES" ]] || {
      echo "Working tree section in $f has $nonblank non-blank lines, cap is $PERSONA_WORKING_TREE_MAX_LINES"
      echo "(the cap exists so re-inlining the canonical body trips the test"
      echo " even when the link is preserved. If the stub legitimately needs"
      echo " to grow, raise PERSONA_WORKING_TREE_MAX_LINES with a comment.)"
      echo "section body:"
      echo "$section" | sed 's/^/    /'
      return 1
    }
  done
}
