#!/usr/bin/env bats

# Pins three SKILL.md contract points that fail silently at runtime when they
# drift: helper paths must resolve against the skill install dir, Step 3 must
# not prompt on an existing state file, and §4c must name the script that
# computes shallow_review (an orchestrator that hand-rolls it emits [] and
# disables the forced-adversary branch).

load test_helper

skill_section() {
  # $1 is the heading prefix, e.g. '### Step 3: ' or '#### 4c. '
  awk -v h="$1" 'index($0, h)==1 {f=1; next} /^#{3,4} / {f=0} f' "${REPO_ROOT}/SKILL.md"
}

@test "SKILL.md defines SKILL_ROOT in Step 1 and prefixes every helper invocation" {
  step1="$(skill_section '### Step 1: ')"
  grep -q 'SKILL_ROOT' <<<"$step1"
  # a bare `bash scripts/` or `python3 scripts/` resolves against the PR checkout and runs
  # whatever that repo keeps there. change-map.md and generators.md are maintainer docs run
  # from this repo, so their bare paths are correct.
  run grep -nE '(^|[^$"/])(bash|python3?) +["'"'"']?(\./)?scripts/' \
    "${REPO_ROOT}/SKILL.md" \
    "${REPO_ROOT}"/ci-integrations/*.md \
    $(ls "${REPO_ROOT}"/docs/*.md | grep -vE 'change-map|generators')
  [ "$status" -eq 1 ]
}

@test "Step 3 resumes an existing state file via Step 3.6 without offering a choice" {
  step3="$(skill_section '### Step 3: ')"
  ! grep -qi 'offer' <<<"$step3"
  grep -q 'resume: Step 3.5 applies its resume rules first' <<<"$step3"
  grep -q 'then Step 3.6 dispatches' <<<"$step3"
  ! grep -q 'resume or reset' "${REPO_ROOT}/scripts/state_init.sh"
  ! grep -q 'must be skipped on resume' "${REPO_ROOT}/scripts/state_init.sh"
  grep -q "apply Step 3.5's resume rules" "${REPO_ROOT}/scripts/state_init.sh"
}

@test "§4c names flag_shallow_reviews.py and its stdin/stdout shape" {
  sec="$(skill_section '#### 4c. ')"
  grep -q 'flag_shallow_reviews\.py' <<<"$sec"
  grep -q 'stdin JSON array in' <<<"$sec"
  grep -qF '{"shallow_review": [...]}' <<<"$sec"
}
