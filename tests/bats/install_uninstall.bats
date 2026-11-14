#!/usr/bin/env bats

load test_helper

@test "cursor copy fallback removes a partially hardlinked directory" {
  local src="${BATS_TEST_TMPDIR}/skill"
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local target="${fakehome}/.cursor/skills/pr-review-loop"
  mkdir -p "$src/scripts"
  cp "${REPO_ROOT}/install.sh" "$src/install.sh"
  printf 'fixture\n' >"$src/SKILL.md"
  printf 'echo required\n' >"$src/scripts/required.sh"
  stub_cmd cp '
    if [[ "$1" == -al && -d "$2" ]]; then
      mkdir -p "$3"
      touch "$3/partial"
      exit 1
    fi
    exec /bin/cp "$@"'

  HOME="$fakehome" XDG_CONFIG_HOME="$fakehome/.config" CODEX_HOME="$fakehome/.codex" run bash "$src/install.sh" --cursor

  [[ "$status" -eq 0 ]]
  [[ "$output" == *"hardlink + copy"* ]]
  cmp "$src/scripts/required.sh" "$target/scripts/required.sh"
  [[ ! -e "$target/scripts/scripts" ]]
  [[ ! -e "$target/scripts/partial" ]]
}

@test "uninstall preserves foreign dot symlinks when run from the source" {
  local fakehome="${BATS_TEST_TMPDIR}/home" host
  for host in .cursor .claude .codex .agents .config/opencode; do
    mkdir -p "$fakehome/$host/skills"
    ln -s . "$fakehome/$host/skills/pr-review-loop"
  done
  cd "$REPO_ROOT" || return 1

  HOME="$fakehome" XDG_CONFIG_HOME="$fakehome/.config" CODEX_HOME="$fakehome/.codex" run bash ./install.sh --uninstall

  [[ "$status" -eq 0 ]]
  for host in .cursor .claude .codex .agents .config/opencode; do
    [[ -L "$fakehome/$host/skills/pr-review-loop" ]]
    [[ "$(readlink "$fakehome/$host/skills/pr-review-loop")" == . ]]
  done
}

@test "uninstall resolves an owned relative symlink from its parent" {
  local src="${BATS_TEST_TMPDIR}/skill"
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "$src" "$fakehome/.claude/skills"
  cp "${REPO_ROOT}/install.sh" "$src/install.sh"
  ln -s ../../../skill "$fakehome/.claude/skills/pr-review-loop"

  HOME="$fakehome" XDG_CONFIG_HOME="$fakehome/.config" CODEX_HOME="$fakehome/.codex" run bash "$src/install.sh" --uninstall

  [[ "$status" -eq 0 ]]
  [[ ! -L "$fakehome/.claude/skills/pr-review-loop" ]]
  [[ "$output" == *"removed symlink:"* ]]
}

@test "uninstall leaves a non-symlink at target alone" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${fakehome}/.cursor/skills" "${fakehome}/.claude/skills" "${fakehome}/.codex/skills"
  echo "user file" > "${fakehome}/.cursor/skills/pr-review-loop"
  echo "codex file" > "${fakehome}/.codex/skills/pr-review-loop"
  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --uninstall
  [[ "$status" -eq 0 ]]
  [[ -f "${fakehome}/.cursor/skills/pr-review-loop" ]]
  [[ ! -L "${fakehome}/.cursor/skills/pr-review-loop" ]]
  [[ "$(cat "${fakehome}/.cursor/skills/pr-review-loop")" == "user file" ]]
  [[ -f "${fakehome}/.codex/skills/pr-review-loop" ]]
  [[ ! -L "${fakehome}/.codex/skills/pr-review-loop" ]]
  [[ "$(cat "${fakehome}/.codex/skills/pr-review-loop")" == "codex file" ]]
  [[ "$output" == *"skipped (not a symlink): ${fakehome}/.codex/skills/pr-review-loop (Codex)"* ]]
  [[ "$output" == *"skipped (not our install): ${fakehome}/.cursor/skills/pr-review-loop (Cursor)"* ]]
}

@test "cursor install creates hardlink tree with source marker" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor

  [[ "$status" -eq 0 ]]
  [[ -d "${fakehome}/.cursor/skills/pr-review-loop" ]]
  [[ ! -L "${fakehome}/.cursor/skills/pr-review-loop" ]]
  [[ "$(<"${fakehome}/.cursor/skills/pr-review-loop/.pr-review-loop-source")" == "${REPO_ROOT_PHYSICAL}" ]]
  [[ ! -e "${fakehome}/.cursor/skills/pr-review-loop/.git" ]]
  [[ "$output" == *"installed ("*"(Cursor)"* ]]
  # select_host must clear WANT_OPENCODE too: a host-flagged run may not
  # touch opencode paths at all.
  [[ ! -e "${fakehome}/.config/opencode" ]]
}

@test "cursor uninstall removes legacy symlink with logical path" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local logical="${BATS_TEST_TMPDIR}/logical-repo"
  mkdir -p "${fakehome}/.cursor/skills" "$logical"
  ln -s "${REPO_ROOT}" "$logical/link"
  ln -s "$logical/link" "${fakehome}/.cursor/skills/pr-review-loop"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --uninstall
  [[ "$status" -eq 0 ]]
  [[ ! -e "${fakehome}/.cursor/skills/pr-review-loop" ]]
  [[ "$output" == *"removed symlink:"* ]]
}

@test "cursor uninstall preserves foreign symlink" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local other="${BATS_TEST_TMPDIR}/other"
  mkdir -p "${fakehome}/.cursor/skills" "$other"

  ln -s "$other" "${fakehome}/.cursor/skills/pr-review-loop"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --uninstall
  [[ "$status" -eq 0 ]]
  [[ -L "${fakehome}/.cursor/skills/pr-review-loop" ]]
  [[ "$(readlink "${fakehome}/.cursor/skills/pr-review-loop")" == "$other" ]]
  [[ "$output" == *"skipped (symlink points elsewhere)"* ]]
}

@test "cursor reinstall refreshes when top-level entry added" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  # Install from an isolated copy of the repo, not REPO_ROOT itself: this
  # test mutates the source tree (adds a file, then reinstalls to prove the
  # refresh picks it up). Mutating REPO_ROOT would race other tests under
  # `bats --jobs` and leave a stray untracked file the manifest-sync tests
  # would trip over.
  local src="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree "$src"
  local added="${src}/.install-refresh-testfile"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  touch "$added"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  [[ -f "${fakehome}/.cursor/skills/pr-review-loop/.install-refresh-testfile" ]]
  [[ "$output" == *"refreshed ("* ]]
}

@test "cursor reinstall is idempotent" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"already installed: ${fakehome}/.cursor/skills/pr-review-loop (Cursor)"* ]]
}

@test "cursor reinstall replaces a stale hardlink when a source file is replaced" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  # Mutates the source tree, so work from an isolated copy (see the
  # "top-level entry added" test for the rationale).
  local src="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree "$src"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  # Replace (not edit-in-place) a tracked file so it gets a fresh inode,
  # breaking the hardlink the install created.
  rm "${src}/SKILL.md"
  printf 'replaced content\n' > "${src}/SKILL.md"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"refreshed ("* ]]
  [[ "$(<"${fakehome}/.cursor/skills/pr-review-loop/SKILL.md")" == "replaced content" ]]
}

@test "cursor reinstall refreshes when a nested file is added" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local src="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree "$src"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  touch "${src}/reviewers/.install-nested-testfile"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"refreshed ("* ]]
  [[ -f "${fakehome}/.cursor/skills/pr-review-loop/reviewers/.install-nested-testfile" ]]
}

@test "--force rebuilds the Cursor tree even when in sync" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor --force
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"refreshed ("* ]]
  [[ -f "${fakehome}/.cursor/skills/pr-review-loop/SKILL.md" ]]
}

@test "--force with no host flag installs all hosts" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --force
  [[ "$status" -eq 0 ]]
  [[ -d "${fakehome}/.cursor/skills/pr-review-loop" ]]
  [[ -L "${fakehome}/.claude/skills/pr-review-loop" ]]
  [[ -L "${fakehome}/.codex/skills/pr-review-loop" ]]
  [[ -L "${fakehome}/.config/opencode/skills/pr-review-loop" ]]
  [[ -L "${fakehome}/.config/opencode/agent/prl-cheap.md" ]]
}

@test "cursor uninstall removes hardlink install without touching source" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --uninstall
  [[ "$status" -eq 0 ]]
  [[ ! -e "${fakehome}/.cursor/skills/pr-review-loop" ]]
  [[ -f "${REPO_ROOT}/SKILL.md" ]]
  [[ "$output" == *"removed Cursor install: ${fakehome}/.cursor/skills/pr-review-loop"* ]]
}

@test "--uninstall targets all hosts even when a host flag is present" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${fakehome}/.cursor" "${fakehome}/.claude" "${fakehome}/.codex" \
    "${fakehome}/.config/opencode"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh"
  [[ "$status" -eq 0 ]]
  [[ -d "${fakehome}/.cursor/skills/pr-review-loop" ]]
  [[ -L "${fakehome}/.claude/skills/pr-review-loop" ]]
  [[ -L "${fakehome}/.codex/skills/pr-review-loop" ]]
  [[ -L "${fakehome}/.config/opencode/skills/pr-review-loop" ]]
  [[ -L "${fakehome}/.config/opencode/agent/prl-strong.md" ]]

  # A host flag must not narrow a removal: --cursor --uninstall removes all.
  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor --uninstall
  [[ "$status" -eq 0 ]]
  [[ ! -e "${fakehome}/.cursor/skills/pr-review-loop" ]]
  [[ ! -e "${fakehome}/.claude/skills/pr-review-loop" ]]
  [[ ! -e "${fakehome}/.codex/skills/pr-review-loop" ]]
  [[ ! -e "${fakehome}/.config/opencode/skills/pr-review-loop" ]]
  [[ ! -e "${fakehome}/.config/opencode/agent/prl-strong.md" ]]
}

@test "bare Codex install fails when only the shared skill link is stale" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local other="${BATS_TEST_TMPDIR}/older-checkout"
  local target="${fakehome}/.agents/skills/pr-review-loop"
  mkdir -p "${fakehome}/.codex" "${fakehome}/.agents/skills" "$other"
  ln -s "$other" "$target"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh"

  [[ "$status" -eq 1 ]]
  [[ "$output" == *"skipped (symlink points elsewhere): $target -> $other (Codex shared skills)"* ]]
  [[ "$output" == *"rerun with --force to replace this symlink"* ]]
  [[ "$output" != *"Done."* ]]
  [[ "$(readlink "$target")" == "$other" ]]
  [[ "$(readlink "${fakehome}/.codex/skills/pr-review-loop")" == "${REPO_ROOT}" ]]

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --codex --force

  [[ "$status" -eq 0 ]]
  [[ "$(readlink "$target")" == "${REPO_ROOT}" ]]
}

@test "codex install links both discovery paths and is idempotent" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --codex

  [[ "$status" -eq 0 ]]
  [[ -L "${fakehome}/.codex/skills/pr-review-loop" ]]
  [[ "$(readlink "${fakehome}/.codex/skills/pr-review-loop")" == "${REPO_ROOT}" ]]
  [[ "$output" == *"linked: ${fakehome}/.codex/skills/pr-review-loop -> ${REPO_ROOT} (Codex)"* ]]
  [[ "$(readlink "${fakehome}/.agents/skills/pr-review-loop")" == "${REPO_ROOT}" ]]
  cmp "${REPO_ROOT}/SKILL.md" "${fakehome}/.agents/skills/pr-review-loop/SKILL.md"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --codex

  [[ "$status" -eq 0 ]]
  [[ "$output" == *"already linked: ${fakehome}/.agents/skills/pr-review-loop (Codex shared skills)"* ]]
  [[ "$(readlink "${fakehome}/.agents/skills/pr-review-loop")" == "${REPO_ROOT}" ]]
}

@test "codex install honors CODEX_HOME" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local fakecodex="${BATS_TEST_TMPDIR}/custom-codex"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakecodex}" run "${REPO_ROOT}/install.sh" --codex

  [[ "$status" -eq 0 ]]
  [[ -L "${fakecodex}/skills/pr-review-loop" ]]
  [[ "$(readlink "${fakecodex}/skills/pr-review-loop")" == "${REPO_ROOT}" ]]
  [[ ! -e "${fakehome}/.codex/skills/pr-review-loop" ]]
  [[ "$(readlink "${fakehome}/.agents/skills/pr-review-loop")" == "${REPO_ROOT}" ]]
}

@test "codex uninstall removes both owned discovery links" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${fakehome}/.codex/skills" "${fakehome}/.agents/skills"
  ln -s "${REPO_ROOT}" "${fakehome}/.codex/skills/pr-review-loop"
  ln -s "${REPO_ROOT}" "${fakehome}/.agents/skills/pr-review-loop"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --uninstall

  [[ "$status" -eq 0 ]]
  [[ ! -e "${fakehome}/.codex/skills/pr-review-loop" ]]
  [[ "$output" == *"removed symlink: ${fakehome}/.codex/skills/pr-review-loop (Codex)"* ]]
  [[ ! -L "${fakehome}/.agents/skills/pr-review-loop" ]]
  [[ "$output" == *"removed symlink: ${fakehome}/.agents/skills/pr-review-loop (Codex shared skills)"* ]]
}

@test "cursor install skips gitignored dev state" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  # Build the dev state in the fixture rather than asserting against REPO_ROOT:
  # CI checks out clean, so a .worktrees assertion there would pass vacuously.
  local src="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree "$src"
  mkdir -p "${src}/.worktrees/some-branch"
  echo "local state" > "${src}/.worktrees/some-branch/file.md"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  [[ ! -e "${fakehome}/.cursor/skills/pr-review-loop/.worktrees" ]]
  [[ -f "${fakehome}/.cursor/skills/pr-review-loop/SKILL.md" ]]
}

@test "cursor reinstall rebuilds a tree still holding a now-excluded path" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local src="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree "$src"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  # Stands in for a tree installed before .worktrees joined CURSOR_INSTALL_SKIP.
  mkdir -p "${fakehome}/.cursor/skills/pr-review-loop/.worktrees/stale"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"refreshed ("* ]]
  [[ ! -e "${fakehome}/.cursor/skills/pr-review-loop/.worktrees" ]]
}

@test "cursor reinstall rebuilds a tree holding a dangling excluded symlink" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local src="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree "$src"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  # cp -a preserves a symlink, so an older install.sh could leave one here.
  # -e alone is false when the target is gone, which would hide it from the guard.
  ln -s "${BATS_TEST_TMPDIR}/gone" "${fakehome}/.cursor/skills/pr-review-loop/.worktrees"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"refreshed ("* ]]
  [[ ! -L "${fakehome}/.cursor/skills/pr-review-loop/.worktrees" ]]
}

@test "cursor reinstall keeps a copy-fallback install when content still matches" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local src="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree "$src"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  # Break the hardlink without changing the bytes, the shape a copy-fallback
  # install on another volume leaves behind: the ids differ but cmp agrees, so
  # the tree is in sync and must not be rebuilt.
  local installed="${fakehome}/.cursor/skills/pr-review-loop/SKILL.md"
  cp "$installed" "${BATS_TEST_TMPDIR}/keep"
  rm "$installed"
  cp "${BATS_TEST_TMPDIR}/keep" "$installed"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"already installed"* ]]
}

@test "install.sh avoids bash 4 only constructs" {
  # macOS ships bash 3.2 as /bin/bash and install.sh runs under whatever bash
  # resolves first, so an associative array breaks the freshness check on a
  # stock mac. CI runs bash 5, which cannot catch it behaviourally.
  run grep -nE '(local|declare)[[:space:]]+-[A-Za-z]*A' "${REPO_ROOT}/install.sh"
  [[ "$status" -ne 0 ]] || {
    echo "associative array in install.sh (bash 4+ only): $output"
    return 1
  }
}

@test "cursor install omits nested build caches" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local src="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree "$src"
  # cp -al recurses unfiltered, so a top-level-only skip list can never reach
  # these. Two locations, because one would pass against a rule hardcoding it.
  mkdir -p "${src}/scripts/__pycache__" "${src}/tools/recall-harness/tests/__pycache__"
  touch "${src}/scripts/__pycache__/x.pyc" \
    "${src}/tools/recall-harness/tests/__pycache__/y.pyc"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  local target="${fakehome}/.cursor/skills/pr-review-loop"
  [[ ! -e "${target}/scripts/__pycache__" ]]
  [[ ! -e "${target}/tools/recall-harness/tests/__pycache__" ]]
  [[ -f "${target}/scripts/promote_findings.py" ]]
}

@test "cursor install omits nested excluded paths" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local src="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree "$src"
  mkdir -p "${src}/docs/superpowers/plans" "${src}/tools/recall-harness/corpus"
  touch "${src}/docs/superpowers/plans/p.md" "${src}/tools/recall-harness/corpus/c.json"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  local target="${fakehome}/.cursor/skills/pr-review-loop"
  [[ ! -e "${target}/docs/superpowers" ]]
  [[ ! -e "${target}/tools/recall-harness/corpus" ]]
  # siblings of the excluded prefixes must survive, or the rule over-matched.
  [[ -f "${target}/docs/change-map.md" ]]
  [[ -f "${target}/tools/recall-harness/report.py" ]]
}

@test "cursor reinstall rebuilds a tree holding a stale nested excluded path" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local src="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree "$src"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  # Both sides of the path-set comparison prune this, so without a dedicated
  # guard the install reports "already installed" forever and never drops it.
  local target="${fakehome}/.cursor/skills/pr-review-loop"
  mkdir -p "${target}/scripts/__pycache__"
  touch "${target}/scripts/__pycache__/stale.pyc"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"refreshed ("* ]]
  [[ ! -e "${target}/scripts/__pycache__" ]]
}

@test "cursor install ships no gitignored files" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local src="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree --git "$src"
  mkdir -p "${src}/.superpowers/sdd"
  printf '*\n' >"${src}/.superpowers/sdd/.gitignore"
  printf 'execution scratch\n' >"${src}/.superpowers/sdd/session.md"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  # Assert the result rather than the mechanism, so this stays valid if the
  # skip rule is ever restructured.
  local target="${fakehome}/.cursor/skills/pr-review-loop"
  local ignored
  ignored="$(cd "$target" && find . -type f ! -name '.pr-review-loop-source' |
    sed 's|^\./||' | git -C "$src" check-ignore --no-index --stdin || true)"
  [[ -z "$ignored" ]] || {
    echo "gitignored files installed:"
    echo "$ignored"
    return 1
  }
}

@test "bare install skips undetected hosts" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${fakehome}/.claude"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh"

  [[ "$status" -eq 0 ]]
  [[ -L "${fakehome}/.claude/skills/pr-review-loop" ]]
  [[ ! -e "${fakehome}/.cursor" ]]
  [[ ! -e "${fakehome}/.codex" ]]
  [[ ! -e "${fakehome}/.config/opencode/skills/pr-review-loop" ]]
}

@test "bare install with nothing detected prints probed paths and exits 0" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${fakehome}"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh"

  [[ "$status" -eq 0 ]]
  [[ "$output" == *"no supported hosts detected"* ]]
  [[ "$output" == *"${fakehome}/.cursor"* ]]
  [[ "$output" == *"--opencode"* ]]
  [[ -z "$(ls -A "$fakehome")" ]]
}

@test "opencode install forces targets without detection" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --opencode

  [[ "$status" -eq 0 ]]
  [[ -L "${fakehome}/.config/opencode/skills/pr-review-loop" ]]
  local agent
  for agent in prl-cheap prl-standard prl-strong; do
    [[ -L "${fakehome}/.config/opencode/agent/${agent}.md" ]]
    [[ -f "${fakehome}/.config/opencode/agent/${agent}.md" ]]
  done
}

@test "opencode uninstall removes skill and tier agent links without touching source" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --opencode
  [[ "$status" -eq 0 ]]

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --uninstall
  [[ "$status" -eq 0 ]]
  [[ ! -e "${fakehome}/.config/opencode/skills/pr-review-loop" ]]
  local agent
  for agent in prl-cheap prl-standard prl-strong; do
    [[ ! -e "${fakehome}/.config/opencode/agent/${agent}.md" ]]
  done
  [[ -f "${REPO_ROOT}/hosts/opencode/agent/prl-cheap.md" ]]
}

@test "a foreign regular file at one host target warns without blocking the other hosts" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${fakehome}/.cursor" "${fakehome}/.claude/skills" "${fakehome}/.codex" \
    "${fakehome}/.config/opencode"
  echo "user file" > "${fakehome}/.claude/skills/pr-review-loop"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh"

  [[ "$status" -eq 1 ]]
  [[ "$output" == *"${fakehome}/.claude/skills/pr-review-loop exists and is not a symlink"* ]]
  [[ -d "${fakehome}/.cursor/skills/pr-review-loop" ]]
  [[ -L "${fakehome}/.codex/skills/pr-review-loop" ]]
  [[ -L "${fakehome}/.config/opencode/skills/pr-review-loop" ]]
  [[ "$(cat "${fakehome}/.claude/skills/pr-review-loop")" == "user file" ]]
}

@test "opencode agent install refuses to clobber a foreign file and keeps the rest" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${fakehome}/.config/opencode/agent"
  echo "user agent" > "${fakehome}/.config/opencode/agent/prl-cheap.md"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --opencode

  [[ "$status" -eq 1 ]]
  [[ "$output" == *"opencode agent prl-cheap"* ]]
  [[ "$(cat "${fakehome}/.config/opencode/agent/prl-cheap.md")" == "user agent" ]]
  [[ -L "${fakehome}/.config/opencode/skills/pr-review-loop" ]]
  [[ -L "${fakehome}/.config/opencode/agent/prl-standard.md" ]]
  [[ -L "${fakehome}/.config/opencode/agent/prl-strong.md" ]]
}

@test "opencode reinstall is idempotent and --force relinks" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --opencode
  [[ "$status" -eq 0 ]]

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --opencode
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"already linked: ${fakehome}/.config/opencode/agent/prl-cheap.md"* ]]

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --opencode --force
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"re-linked: ${fakehome}/.config/opencode/agent/prl-cheap.md"* ]]
}

@test "install refuses foreign symlinks at link_one targets; --force re-establishes" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local other="${BATS_TEST_TMPDIR}/other"
  mkdir -p "${fakehome}/.claude/skills" "${fakehome}/.config/opencode/skills" "${fakehome}/.agents/skills" "$other"
  ln -s "$other" "${fakehome}/.claude/skills/pr-review-loop"
  ln -s "$other" "${fakehome}/.config/opencode/skills/pr-review-loop"
  ln -s "$other" "${fakehome}/.agents/skills/pr-review-loop"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --claude --codex --opencode

  [[ "$status" -eq 1 ]]
  [[ "$(readlink "${fakehome}/.claude/skills/pr-review-loop")" == "$other" ]]
  [[ "$(readlink "${fakehome}/.config/opencode/skills/pr-review-loop")" == "$other" ]]
  [[ "$(readlink "${fakehome}/.agents/skills/pr-review-loop")" == "$other" ]]
  [[ "$output" == *"rerun with --force to replace this symlink"* ]]
  # the refusal must not stop the rest of the opencode host
  [[ -L "${fakehome}/.config/opencode/agent/prl-cheap.md" ]]

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --claude --codex --opencode --force

  [[ "$status" -eq 0 ]]
  [[ "$(readlink "${fakehome}/.claude/skills/pr-review-loop")" == "${REPO_ROOT}" ]]
  [[ "$(readlink "${fakehome}/.config/opencode/skills/pr-review-loop")" == "${REPO_ROOT}" ]]
  [[ "$(readlink "${fakehome}/.agents/skills/pr-review-loop")" == "${REPO_ROOT}" ]]
}

@test "opencode agent install refuses a foreign symlink and keeps the rest" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local other="${BATS_TEST_TMPDIR}/other"
  mkdir -p "${fakehome}/.config/opencode/agent" "$other"
  echo "user agent" > "$other/prl-cheap.md"
  ln -s "$other/prl-cheap.md" "${fakehome}/.config/opencode/agent/prl-cheap.md"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --opencode

  [[ "$status" -eq 1 ]]
  [[ "$output" == *"skipped (symlink points elsewhere): ${fakehome}/.config/opencode/agent/prl-cheap.md"* ]]
  [[ "$(readlink "${fakehome}/.config/opencode/agent/prl-cheap.md")" == "$other/prl-cheap.md" ]]
  [[ -L "${fakehome}/.config/opencode/skills/pr-review-loop" ]]
  [[ -L "${fakehome}/.config/opencode/agent/prl-standard.md" ]]
}

@test "a failing link surfaces in the exit code without a success line" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${fakehome}/.claude/skills"
  chmod 555 "${fakehome}/.claude/skills"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --claude
  local rc="$status"
  chmod 755 "${fakehome}/.claude/skills"

  [[ "$rc" -eq 1 ]]
  [[ "$output" == *"ERROR: failed to link"* ]]
  [[ "$output" != *"linked: "* ]]
}

@test "a failing agent-dir rm surfaces in the uninstall exit code" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --opencode
  [[ "$status" -eq 0 ]]
  chmod 555 "${fakehome}/.config/opencode/agent"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --uninstall
  local rc=$status
  chmod 755 "${fakehome}/.config/opencode/agent"

  [[ "$rc" -eq 1 ]]
  [[ "$output" == *"ERROR: cannot remove ${fakehome}/.config/opencode/agent/prl-cheap.md"* ]]
  [[ ! "$output" == *"removed symlink: ${fakehome}/.config/opencode/agent/prl-cheap.md"* ]]
  [[ -L "${fakehome}/.config/opencode/agent/prl-cheap.md" ]]
  # the skill link sits in a writable dir and must still be removed
  [[ ! -e "${fakehome}/.config/opencode/skills/pr-review-loop" ]]
}

@test "uninstall preserves foreign symlinks at skill and agent targets" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local other="${BATS_TEST_TMPDIR}/other"
  mkdir -p "${fakehome}/.claude/skills" "${fakehome}/.config/opencode/agent" "$other"
  ln -s "$other" "${fakehome}/.claude/skills/pr-review-loop"
  echo "user agent" > "$other/prl-cheap.md"
  ln -s "$other/prl-cheap.md" "${fakehome}/.config/opencode/agent/prl-cheap.md"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --uninstall

  [[ "$status" -eq 0 ]]
  [[ "$(readlink "${fakehome}/.claude/skills/pr-review-loop")" == "$other" ]]
  [[ "$(readlink "${fakehome}/.config/opencode/agent/prl-cheap.md")" == "$other/prl-cheap.md" ]]
}

@test "a failing agent link surfaces in the exit code and keeps the skill link" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${fakehome}/.config/opencode/agent"
  chmod 555 "${fakehome}/.config/opencode/agent"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --opencode
  local rc=$status
  chmod 755 "${fakehome}/.config/opencode/agent"

  [[ "$rc" -eq 1 ]]
  [[ "$output" == *"ERROR: failed to link ${fakehome}/.config/opencode/agent/prl-cheap.md"* ]]
  [[ ! "$output" == *"linked: ${fakehome}/.config/opencode/agent/"* ]]
  [[ -L "${fakehome}/.config/opencode/skills/pr-review-loop" ]]
}

@test "opencode install honors XDG_CONFIG_HOME outside the home dir" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local xdg="${BATS_TEST_TMPDIR}/xdg"
  mkdir -p "$xdg/opencode"

  HOME="${fakehome}" XDG_CONFIG_HOME="$xdg" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --opencode

  [[ "$status" -eq 0 ]]
  [[ -L "$xdg/opencode/skills/pr-review-loop" ]]
  [[ -L "$xdg/opencode/agent/prl-cheap.md" ]]
  [[ ! -e "${fakehome}/.config/opencode" ]]
}

@test "bare install detects CODEX_HOME outside the home dir" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local fakecodex="${BATS_TEST_TMPDIR}/xdg-codex"
  mkdir -p "$fakecodex"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="$fakecodex" run "${REPO_ROOT}/install.sh"

  [[ "$status" -eq 0 ]]
  [[ -L "$fakecodex/skills/pr-review-loop" ]]
  [[ ! -e "${fakehome}/.codex/skills/pr-review-loop" ]]
  [[ "$(readlink "${fakehome}/.agents/skills/pr-review-loop")" == "${REPO_ROOT}" ]]
}

@test "a failing link_one uninstall rm surfaces in the exit code" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${fakehome}/.claude/skills"
  ln -s "${REPO_ROOT}" "${fakehome}/.claude/skills/pr-review-loop"
  chmod 555 "${fakehome}/.claude/skills"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --uninstall
  local rc=$status
  chmod 755 "${fakehome}/.claude/skills"

  [[ "$rc" -eq 1 ]]
  [[ "$output" == *"ERROR: cannot remove ${fakehome}/.claude/skills/pr-review-loop (Claude Code)"* ]]
  [[ ! "$output" == *"removed symlink: ${fakehome}/.claude/skills/pr-review-loop"* ]]
  [[ -L "${fakehome}/.claude/skills/pr-review-loop" ]]
}

@test "a failing cursor uninstall rm -rf surfaces in the exit code" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  chmod 555 "${fakehome}/.cursor/skills"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --uninstall
  local rc=$status
  # Non-recursive restore on purpose: only skills is restricted, and a
  # guard-skipped rm -rf leaves the hardlinked tree intact, where chmod -R
  # would flip REPO_ROOT source modes through the shared inodes.
  chmod 755 "${fakehome}/.cursor/skills"

  [[ "$rc" -eq 1 ]]
  [[ "$output" == *"ERROR: cannot remove ${fakehome}/.cursor/skills/pr-review-loop (Cursor)"* ]]
  [[ ! "$output" == *"removed Cursor install"* ]]
  [[ -d "${fakehome}/.cursor/skills/pr-review-loop" ]]
}

@test "a failing cursor force-rebuild rm -rf surfaces in the exit code" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  chmod 555 "${fakehome}/.cursor/skills"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor --force
  local rc=$status
  chmod 755 "${fakehome}/.cursor/skills"

  [[ "$rc" -eq 1 ]]
  [[ "$output" == *"ERROR: cannot remove ${fakehome}/.cursor/skills/pr-review-loop (Cursor)"* ]]
  [[ ! "$output" == *"refreshed"* ]]
}

@test "a failing cursor legacy-symlink rm surfaces in the exit code" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${fakehome}/.cursor/skills"
  ln -s "${REPO_ROOT}" "${fakehome}/.cursor/skills/pr-review-loop"
  chmod 555 "${fakehome}/.cursor/skills"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --uninstall
  local rc=$status
  chmod 755 "${fakehome}/.cursor/skills"

  [[ "$rc" -eq 1 ]]
  [[ "$output" == *"ERROR: cannot remove ${fakehome}/.cursor/skills/pr-review-loop (Cursor)"* ]]
  [[ -L "${fakehome}/.cursor/skills/pr-review-loop" ]]
}

@test "a failing cursor marker write surfaces in the exit code" {
  local fakehome="${BATS_TEST_TMPDIR}/home"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor
  [[ "$status" -eq 0 ]]
  rm "${fakehome}/.cursor/skills/pr-review-loop/.pr-review-loop-source"
  chmod 555 "${fakehome}/.cursor/skills/pr-review-loop"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor
  local rc=$status
  chmod 755 "${fakehome}/.cursor/skills/pr-review-loop"

  [[ "$rc" -eq 1 ]]
  [[ "$output" == *"ERROR: cannot write marker"* ]]
  [[ ! "$output" == *"already installed"* ]]
}

@test "failing force-path removals surface in the exit code" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local other="${BATS_TEST_TMPDIR}/other"
  mkdir -p "${fakehome}/.claude/skills" "${fakehome}/.config/opencode/agent" "$other"
  echo "x" > "$other/somewhere"
  ln -s "$other" "${fakehome}/.claude/skills/pr-review-loop"
  ln -s "$other/somewhere" "${fakehome}/.config/opencode/agent/prl-cheap.md"
  chmod 555 "${fakehome}/.claude/skills" "${fakehome}/.config/opencode/agent"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --claude --opencode --force
  local rc=$status
  chmod 755 "${fakehome}/.claude/skills" "${fakehome}/.config/opencode/agent"

  [[ "$rc" -eq 1 ]]
  [[ "$output" == *"ERROR: cannot remove ${fakehome}/.claude/skills/pr-review-loop (Claude Code)"* ]]
  [[ "$output" == *"ERROR: cannot remove ${fakehome}/.config/opencode/agent/prl-cheap.md"* ]]
  [[ "$(readlink "${fakehome}/.claude/skills/pr-review-loop")" == "$other" ]]
  [[ "$(readlink "${fakehome}/.config/opencode/agent/prl-cheap.md")" == "$other/somewhere" ]]
}

@test "a failing cursor install-path legacy-symlink rm surfaces in the exit code" {
  local fakehome="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${fakehome}/.cursor/skills"
  ln -s "${REPO_ROOT}" "${fakehome}/.cursor/skills/pr-review-loop"
  chmod 555 "${fakehome}/.cursor/skills"

  HOME="${fakehome}" XDG_CONFIG_HOME="${fakehome}/.config" CODEX_HOME="${fakehome}/.codex" run "${REPO_ROOT}/install.sh" --cursor
  local rc=$status
  chmod 755 "${fakehome}/.cursor/skills"

  [[ "$rc" -eq 1 ]]
  [[ "$output" == *"ERROR: cannot remove ${fakehome}/.cursor/skills/pr-review-loop (Cursor)"* ]]
  [[ ! "$output" == *"installed ("* ]]
  [[ "$(readlink "${fakehome}/.cursor/skills/pr-review-loop")" == "${REPO_ROOT}" ]]
}
