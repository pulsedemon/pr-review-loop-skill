#!/usr/bin/env bats

# Move C lives canonically in docs/procedure-moves.md. The personas with
# move_c: true in reviewers/personas.yaml inline a one-line severity
# paraphrase plus a link to that doc; the canonical body is not copied
# into the persona stubs. This test pins three things:
#
#   1. Canonical-doc shape — procedure-moves.md keeps the numbered
#      contract-drift list with the three named patterns (terminology
#      drift, contract drift, schema-constraint), and the severity
#      prose pinned by test_skill_move_c_persona_sync.bats co-locates
#      with the right rule (terminology drift → blocker, schema
#      constraint → Always `suggestion`, doc-as-contract → blocker).
#      Structural assertions, not English-prose canaries: a reasonable
#      editorial rewrite preserves the structure even when it
#      paraphrases the surrounding sentence.
#   2. Persona link integrity — every move_c persona's "Procedure
#      move C" section contains a markdown link whose relative target
#      resolves to docs/procedure-moves.md on disk. A broken path
#      (typo, directory move) fails here rather than at runtime.
#   3. Persona stub size + canonical-only canaries — each section is
#      short (re-inlining the ~20-line canonical body would exceed
#      the cap) and does not contain phrases that live only in the
#      canonical body. The two together catch copy-paste-back even
#      when the link is preserved.
#
# Limitation (intentional): paraphrased per-persona overrides that
# don't quote any canary phrase are NOT caught. The cap on section
# size is the only guard against partial re-inlining via paraphrase;
# pure single-line overrides are invisible. The cap was chosen wide
# enough to allow the SKILL.md §4b severity one-liner that personas
# inline today.
#
# Adversary's Move C inheritance is checked separately at the bottom:
# adversary.md is not in the move_c manifest (which drives the
# extraction guard, not the inheritance contract) but its prompt
# must still carry a pointer to the canonical doc.

load test_helper

CANONICAL_PATH_FROM_REPO="docs/procedure-moves.md"
CANONICAL="${REPO_ROOT}/${CANONICAL_PATH_FROM_REPO}"

# Maximum non-blank line count for a persona's Move C section. The
# stub today is the heading + a one-line severity paraphrase + a
# link, so ~6 non-blank lines is plenty. The canonical body is 18+
# non-blank lines; a re-inline trips this cap. If the inline severity
# rules legitimately need to grow past this, raise the cap with a
# comment explaining why — don't silently bump it.
PERSONA_MOVE_C_MAX_LINES=10

# Extract the Move C section from a reviewer file. Starts at the
# "## Procedure move C" heading, ends at the next "## " heading.
_extract_persona_move_c() {
  local file="$1"
  awk '
    /^## Procedure move C/ { capturing = 1 }
    capturing && /^## / && !/^## Procedure move C/ { capturing = 0 }
    capturing { print }
  ' "$file"
}

# Resolve the Move C personas from the manifest, expressed as
# absolute paths to their persona files. A single change in
# reviewers/personas.yaml (e.g. flipping move_c: true on a new
# persona) extends every assertion in this file automatically.
_move_c_files() {
  local f
  while read -r f; do
    printf '%s\n' "${REPO_ROOT}/reviewers/${f}"
  done < <(python3 "${SCRIPTS}/personas_manifest.py" --list move-c-files)
}

@test "Move C: manifest reports at least 1 Move C file (link-presence check is non-vacuous)" {
  local count
  count=$(python3 "${SCRIPTS}/personas_manifest.py" --list move-c-files | wc -l | tr -d ' ')
  [[ "$count" -ge 1 ]] || {
    echo "manifest reports $count Move C files; the link-presence + canary"
    echo "checks below have nothing to assert against. Either flip move_c: true"
    echo "on at least one persona in reviewers/personas.yaml, or delete this"
    echo "test if Move C is no longer used."
    return 1
  }
}

@test "Move C: canonical doc exists at docs/procedure-moves.md" {
  [[ -f "$CANONICAL" ]] || {
    echo "canonical Move C doc not found at $CANONICAL"
    echo "(this doc is where the Move C body lives after the SKILL.md split;"
    echo " personas link to it from their Procedure move C section)"
    return 1
  }
}

@test "Move C: canonical doc carries the numbered contract-drift list with three named patterns" {
  # The contract guarantees the move's body keeps its three-pattern
  # structure: terminology drift, contract drift (same terms,
  # partial enforcement), schema-constraint drift. The numbered list
  # is what the reviewer prompt expects to find. Bullets are not
  # case-sensitive here — the rule names are. Match the structural
  # shape (an "N. **Name**" pattern) rather than a single phrase so
  # editorial rewrites that paraphrase the surrounding sentence still
  # pass as long as the named buckets stand.
  grep -qE '^1\. \*\*Terminology drift' "$CANONICAL" || {
    echo "canonical Move C doc missing the '1. **Terminology drift**' numbered item"
    echo "  — the canonical body must keep its three-pattern numbered structure"
    echo "    (terminology drift, contract drift, schema-constraint) so the"
    echo "    reviewer prompt has a stable shape to read."
    return 1
  }
  grep -qE '^2\. \*\*Contract drift' "$CANONICAL" || {
    echo "canonical Move C doc missing the '2. **Contract drift**' numbered item"
    return 1
  }
  # The schema-constraint pattern lives as a sub-bullet under
  # "Contract drift". Match it specifically — it carries the
  # `type_design` cross-ref obligation and the always-`suggestion`
  # severity pin.
  grep -qE '^[[:space:]]+- Spec/schema documents a constraint' "$CANONICAL" || {
    echo "canonical Move C doc missing the schema-constraint sub-bullet"
    echo "  (expected an indented bullet starting with 'Spec/schema documents a constraint')"
    return 1
  }
}

@test "Move C: canonical doc co-locates severity prose with the right rule (cross-spec with SKILL.md)" {
  # test_skill_move_c_persona_sync.bats pins four severity phrases
  # in SKILL.md's '**Move C' bullet:
  #   - terminology drift → blocker
  #   - schema-constraint sub-bullet → always suggestion
  #   - type_design owns the blocker for that pattern
  #   - doc-as-contract → blocker
  # If SKILL.md says one thing and the canonical body says another,
  # the two specs lie about each other. Mirror the pins here
  # against procedure-moves.md so they cannot drift independently.

  # 1. Terminology drift line carries `blocker` severity. The
  # numbered item starts with "1. **Terminology drift" and runs to
  # the next blank line or the next numbered item; the severity
  # phrase must appear inside it.
  local term_block
  term_block=$(awk '
    /^1\. \*\*Terminology drift/ { capturing = 1 }
    capturing && /^[0-9]+\. / && !/^1\. \*\*Terminology drift/ { capturing = 0 }
    capturing && /^$/ { capturing = 0 }
    capturing { print }
  ' "$CANONICAL")
  [[ -n "$term_block" ]] || {
    echo "could not extract the terminology-drift block from $CANONICAL"
    echo "  — the awk anchor '1. **Terminology drift' no longer matches. the severity"
    echo "    pins below are unverifiable until the anchor is realigned."
    return 1
  }
  echo "$term_block" | grep -q '`blocker`\|severity: blocker' || {
    echo "canonical Move C terminology-drift item does not carry a `blocker` severity tag"
    echo "  SKILL.md pins 'terminology drift (blocker)'; the canonical body must say the same."
    echo "  terminology-drift block from $CANONICAL:"
    echo "$term_block" | sed 's/^/    /'
    return 1
  }

  # 2. Schema-constraint sub-bullet is co-located with the
  # "Always `suggestion`" pin. The bullet starts with
  # "- Spec/schema documents a constraint" and ends at the next
  # sibling sub-bullet or numbered item.
  local schema_bullet
  schema_bullet=$(awk '
    /^[[:space:]]+- Spec\/schema documents a constraint/ { capturing = 1; print; next }
    capturing && /^[[:space:]]+- / { capturing = 0 }
    capturing && /^[0-9]+\. / { capturing = 0 }
    capturing && /^$/ { capturing = 0 }
    capturing { print }
  ' "$CANONICAL")
  [[ -n "$schema_bullet" ]] || {
    echo "could not extract the schema-constraint sub-bullet from $CANONICAL"
    echo "  — the awk anchor '- Spec/schema documents a constraint' no longer matches. the severity"
    echo "    pins below are unverifiable until the anchor is realigned."
    return 1
  }
  echo "$schema_bullet" | grep -q 'Always `suggestion`' || {
    echo "canonical Move C schema-constraint sub-bullet is not co-located with 'Always \`suggestion\`'"
    echo "  — the severity pin may have been moved to a different sub-bullet,"
    echo "    which would invert the rule's meaning."
    echo "  schema-constraint sub-bullet body:"
    echo "$schema_bullet" | sed 's/^/    /'
    return 1
  }
  # 2b. The same sub-bullet must instruct cross-referencing
  # `type_design` in `detail` — SKILL.md §4b's persona one-liner now
  # carries that obligation and the canonical body must back it.
  echo "$schema_bullet" | grep -q 'Cross-reference `type_design`' || {
    echo "canonical Move C schema-constraint sub-bullet does not instruct cross-referencing type_design"
    echo "  — without it synthesis has no dedupe signal between the Move C finding"
    echo "    and type_design's own."
    return 1
  }
  # 2c. Ownership is a separate guarantee from the cross-reference above:
  # it names who escalates. Match the phrase, not the bare persona name —
  # grepping for `type_design` alone passes even if the sentence is
  # inverted to say it does not own the blocker.
  echo "$schema_bullet" | grep -q '`type_design` owns the blocker' || {
    echo "canonical Move C schema-constraint sub-bullet does not pin type_design ownership"
    echo "  — SKILL.md §4b says 'type_design owns the blocker for that pattern';"
    echo "    the canonical body must say the same or the two specs disagree."
    return 1
  }

  # 3. doc-as-contract escalation lives somewhere in the contract-drift
  # block and is colocated with `blocker`. Match against the same
  # block, not against the schema sub-bullet (the schema rule is
  # always `suggestion` regardless of doc-as-contract).
  local contract_block
  contract_block=$(awk '
    /^2\. \*\*Contract drift/ { capturing = 1 }
    capturing && /^[0-9]+\. / && !/^2\. \*\*Contract drift/ { capturing = 0 }
    capturing { print }
  ' "$CANONICAL")
  [[ -n "$contract_block" ]] || {
    echo "could not extract the contract-drift block from $CANONICAL"
    echo "  — the awk anchor '2. **Contract drift' no longer matches. the severity"
    echo "    pins below are unverifiable until the anchor is realigned."
    return 1
  }
  # Scope to the behavior sub-bullet, not the whole block: the
  # schema-constraint sub-bullet says "regardless of doc-as-contract
  # status", which satisfies a block-wide grep even when the escalation
  # rule itself is reworded or dropped.
  local behavior_bullet
  behavior_bullet=$(awk '
    /^[[:space:]]+- Doc claims a behavior/ { capturing = 1; print; next }
    capturing && /^[[:space:]]+- / { capturing = 0 }
    capturing && /^[0-9]+\. / { capturing = 0 }
    capturing && /^$/ { capturing = 0 }
    capturing { print }
  ' "$CANONICAL")
  [[ -n "$behavior_bullet" ]] || {
    echo "could not extract the doc-as-contract behavior sub-bullet from $CANONICAL"
    echo "  — the awk anchor '- Doc claims a behavior' no longer matches."
    return 1
  }
  echo "$behavior_bullet" | grep -q '`blocker` if doc-as-contract' || {
    echo "canonical Move C behavior sub-bullet missing the doc-as-contract escalation"
    echo "  SKILL.md pins 'blocker if doc-as-contract'; the canonical body must record"
    echo "  the same escalation path so readers don't get two different rules."
    echo "  behavior sub-bullet: $behavior_bullet"
    return 1
  }
  echo "$contract_block" | grep -q 'blocker' || {
    echo "canonical Move C contract-drift block has no 'blocker' severity term anywhere"
    echo "  — at minimum the doc-as-contract escalation must mention blocker."
    return 1
  }
}

@test "Move C: every Move C persona pins the schema-constraint severity rule and type_design ownership" {
  # The persona files are the prompts the reviewers actually read at
  # runtime, so an inverted severity rule here changes what the loop
  # does. The link-presence and size-cap checks below cover structure;
  # nothing covered severity content, so flipping "always `suggestion`"
  # to "always `blocker`" in all four passed the whole suite.
  local f section
  while read -r f; do
    section=$(_extract_persona_move_c "$f")
    [[ -n "$section" ]] || {
      echo "could not extract a Move C section from $f"
      return 1
    }
    echo "$section" | grep -q 'schema-constraint sub-bullet always `suggestion`' || {
      echo "$f: Move C section does not pin the schema-constraint severity rule"
      echo "  — SKILL.md and docs/procedure-moves.md both say this pattern is"
      echo "    always \`suggestion\`; a persona saying otherwise files the wrong severity."
      echo "  section: $section"
      return 1
    }
    echo "$section" | grep -q '`type_design` owns that blocker' || {
      echo "$f: Move C section does not pin type_design ownership"
      echo "  — without it the persona has no instruction that type_design, not it,"
      echo "    raises the blocker for the schema-constraint pattern."
      echo "  section: $section"
      return 1
    }
  done < <(_move_c_files)
}

@test "Move C: every Move C persona's section links to the canonical doc on disk" {
  local files=()
  while IFS= read -r line; do
    files+=("$line")
  done < <(_move_c_files)

  local f section link_path persona_dir resolved
  for f in "${files[@]}"; do
    section=$(_extract_persona_move_c "$f")
    [[ -n "$section" ]] || {
      echo "Move C H2 section missing in $f"
      echo "(manifest declares move_c: true for this persona, but the file"
      echo " has no '## Procedure move C' heading)"
      return 1
    }
    # Extract the first markdown link target whose path ends in
    # procedure-moves.md. The link form is [text](relative/path#frag).
    # `grep -oE` returns the parenthesized URL including the trailing ')'.
    link_path=$(echo "$section" \
      | grep -oE '\([^)]*procedure-moves\.md[^)]*\)' \
      | head -1 \
      | sed -E 's/^\(//; s/\)$//; s/#.*$//')
    [[ -n "$link_path" ]] || {
      echo "Move C section in $f does not link to procedure-moves.md"
      echo "(after the SKILL.md split, each move_c persona's Procedure move C"
      echo " section must contain a markdown link [text](path#frag) whose path"
      echo " ends in procedure-moves.md.)"
      echo "section body:"
      echo "$section" | sed 's/^/    /'
      return 1
    }
    # Resolve the link target relative to the persona's directory and
    # confirm the file exists on disk. Catches typos, directory
    # moves, and stale paths that string-only checks miss.
    persona_dir=$(dirname "$f")
    if [[ "$link_path" = /* ]]; then
      resolved="$link_path"
    else
      resolved=$(cd "$persona_dir" && cd "$(dirname "$link_path")" 2>/dev/null && pwd)/$(basename "$link_path")
    fi
    [[ -f "$resolved" ]] || {
      echo "Move C link in $f points at '$link_path' which does not resolve to a file on disk"
      echo "  resolved (from persona dir $persona_dir) to: $resolved"
      return 1
    }
    # Cross-check that the resolved path is the canonical doc, not
    # some other procedure-moves.md elsewhere in the tree.
    local resolved_real expected_real
    resolved_real=$(cd "$(dirname "$resolved")" && pwd)/$(basename "$resolved")
    expected_real=$(cd "$(dirname "$CANONICAL")" && pwd)/$(basename "$CANONICAL")
    [[ "$resolved_real" = "$expected_real" ]] || {
      echo "Move C link in $f resolves to '$resolved_real', not the canonical $expected_real"
      return 1
    }
  done
}

@test "Move C: each persona's Move C section stays at or below the size cap (no full-body re-inline)" {
  local files=()
  while IFS= read -r line; do
    files+=("$line")
  done < <(_move_c_files)

  local f section nonblank
  for f in "${files[@]}"; do
    section=$(_extract_persona_move_c "$f")
    [[ -n "$section" ]] || continue  # section-missing case is handled by the link test
    nonblank=$(echo "$section" | grep -cE '\S' || true)
    [[ "$nonblank" -le "$PERSONA_MOVE_C_MAX_LINES" ]] || {
      echo "Move C section in $f has $nonblank non-blank lines, cap is $PERSONA_MOVE_C_MAX_LINES"
      echo "(this cap exists so re-inlining the canonical body — ~18 non-blank lines —"
      echo " trips the test even when the link is preserved. If the inline severity"
      echo " one-liner legitimately needs to grow past the cap, raise"
      echo " PERSONA_MOVE_C_MAX_LINES with a comment explaining why.)"
      echo "section body:"
      echo "$section" | sed 's/^/    /'
      return 1
    }
  done
}

@test "Move C: persona sections do not contain canonical-only canary phrases (no copy-paste-back)" {
  # Belt-and-suspenders alongside the size cap. These three phrases
  # live only inside the canonical Move C body and are unlikely to
  # show up in a one-line severity paraphrase. If any appears in a
  # persona's Move C section, the body has been re-inlined (with or
  # without keeping the link) and drift is reintroduced. Pinned
  # case-sensitively so a lowercase "always `suggestion`" inside a
  # persona's parenthetical doesn't collide with the canonical
  # "Always `suggestion`".
  local files=()
  while IFS= read -r line; do
    files+=("$line")
  done < <(_move_c_files)

  local canaries=(
    "doc misrepresents the spec"
    "parallel drift"
    "Always \`suggestion\`"
  )

  local f section c
  for f in "${files[@]}"; do
    section=$(_extract_persona_move_c "$f")
    [[ -n "$section" ]] || continue
    for c in "${canaries[@]}"; do
      if echo "$section" | grep -qF "$c"; then
        echo "Move C section in $f appears to inline the canonical body"
        echo "(canary phrase '$c' found; this phrase lives only in"
        echo " docs/procedure-moves.md. The persona's Procedure move C"
        echo " section must stay a short stub, not a copy of the body.)"
        echo "section body:"
        echo "$section" | sed 's/^/    /'
        return 1
      fi
    done
  done
}

@test "Move C: adversary persona prompt references the canonical doc (inheritance pointer)" {
  # reviewers/adversary.md is not in the move_c manifest because
  # adversary inherits all four moves via its own "Procedure moves
  # A/A.1/B/C" section rather than the per-persona Move C extraction
  # convention. But it still needs a pointer to the canonical body;
  # without that pointer the adversary loses its only Move C anchor
  # and the inheritance contract is unenforceable. Guard the
  # pointer separately from the move_c manifest.
  local adv="${REPO_ROOT}/reviewers/adversary.md"
  [[ -f "$adv" ]] || {
    echo "reviewers/adversary.md missing — adversary inheritance contract cannot be checked"
    return 1
  }
  grep -qE '\[.*\]\([^)]*procedure-moves\.md[^)]*\)' "$adv" || {
    echo "reviewers/adversary.md does not contain a markdown link to procedure-moves.md"
    echo "(the adversary inherits Move C and needs the canonical-body pointer in its"
    echo " prompt — see the inheritance note in docs/procedure-moves.md.)"
    return 1
  }
}
