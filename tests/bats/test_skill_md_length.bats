#!/usr/bin/env bats

load test_helper

@test "SKILL.md stays at or below 390 lines" {
  # Cap lowered 406 -> 385 after the contract-thinning PR (#38) moved
  # §3.5 mechanics to docs/pr-scope.md, §4b orchestration to
  # docs/reviewer-orchestration.md, knob rationales to
  # docs/{synthesis,adversary}.md '## ... knobs' sections, and the
  # §4i record-shape inline list to templates/state.schema.json.
  # Cap raised 385 -> 390 by the Tier 1 drift-reduction PR-4 to absorb
  # the §4b Move C cog block's 5-line marker overhead (4 open + 1 close,
  # zero net human prose; see scripts/_move_c_bullet_for_cog.py and
  # docs/generators.md). Each new cog-managed surface adds ~5 marker
  # lines on top of the rendered content; raise this cap with a
  # comment when adding another, never silently. The §4b block now
  # renders four bullets (Moves A/A.1/B/C) instead of one; that needed no
  # raise because it reuses the existing markers and replaced three
  # literal bullets with three rendered ones. The earlier "Reviewer
  # personas" cog block is also accounted for here. Further structural
  # reductions need new content moves, not whitespace tightening.
  local lines
  lines=$(wc -l < "${REPO_ROOT}/SKILL.md")
  [[ "$lines" -le 390 ]] || {
    echo "SKILL.md has $lines lines (cap: 390). Extract more into docs/ or scripts/."
    return 1
  }
}

@test "AGENTS.md stays at or below 50 lines" {
  local lines
  lines=$(wc -l < "${REPO_ROOT}/AGENTS.md")
  [[ "$lines" -le 50 ]] || {
    echo "AGENTS.md has $lines lines (cap: 50). Collapse duplicated SKILL.md content."
    return 1
  }
}
