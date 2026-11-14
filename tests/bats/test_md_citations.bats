#!/usr/bin/env bats
# Guard: markdown path citations resolve. Positive case runs the checker over
# the real repo; negative cases mutation-test it in a temp repo so a silently
# vacuous checker fails here instead of passing forever.

load test_helper

@test "repo markdown citations all resolve from the repo root" {
  cd "$REPO_ROOT"
  run python3 "${SCRIPTS}/check_md_citations.py"
  [[ "$status" -eq 0 ]]
}

@test "backticked citation of an untracked path fails" {
  make_tmp_repo
  printf 'see `docs/nope.md` for details\n' > doc.md
  git add doc.md
  run python3 "${SCRIPTS}/check_md_citations.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"doc.md:1"* ]]
  [[ "$output" == *"docs/nope.md"* ]]
}

@test "file-relative citation fails even when it resolves from the citing file" {
  make_tmp_repo
  mkdir -p sub
  printf 'x\n' > sub/target.md
  printf 'see `target.md#anchor` here\n' > sub/doc.md
  # no violation yet: `target.md` has no slash, so it is not a path citation
  printf 'see `fixtures/f.yaml` too\n' >> sub/doc.md
  mkdir -p sub/fixtures
  printf 'y\n' > sub/fixtures/f.yaml
  git add sub
  run python3 "${SCRIPTS}/check_md_citations.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"sub/doc.md:2"* ]]
  [[ "$output" == *"fixtures/f.yaml"* ]]
}

@test "dead markdown link target fails" {
  make_tmp_repo
  printf 'see [the doc](missing.md)\n' > doc.md
  git add doc.md
  run python3 "${SCRIPTS}/check_md_citations.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"missing.md"* ]]
}

@test "resolving citations, links, placeholders, and allowlisted paths pass" {
  make_tmp_repo
  mkdir -p docs
  printf 'x\n' > docs/real.md
  {
    printf 'see `docs/real.md#anchor` and [real](docs/real.md)\n'
    printf 'template `reviewers/<name>.md` and glob `tests/*.md` are skipped\n'
    printf 'generated `tools/recall-harness/REPORT.md` is allowlisted\n'
    printf 'run `./run.sh` after `git status`\n'
  } > doc.md
  printf 'x\n' > run.sh
  git add doc.md docs run.sh
  run python3 "${SCRIPTS}/check_md_citations.py"
  [[ "$status" -eq 0 ]]
}
