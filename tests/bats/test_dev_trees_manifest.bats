#!/usr/bin/env bats

# Generator gate for the dev-tree skip lists.
#
# manifests/dev-trees.yaml is the source of truth for the dev-only trees
# every consumer skips. scripts/regen_dev_trees.py writes four surfaces from
# it, each in its own syntax. Before the manifest existed the four lists had
# drifted five ways, which is what let .worktrees ship into the Cursor install
# (#77).
#
# Covers the generator contract (docs/generators.md): a canary pinning the
# markers, a drift check, and the cross-consumer sync assertion that is the
# actual point of the manifest.

load test_helper

MANIFEST="manifests/dev-trees.yaml"
GENERATOR="scripts/regen_dev_trees.py"

dev_tree_names() {
  python3 -c "
import sys, yaml
print('\n'.join(yaml.safe_load(open('${REPO_ROOT}/${MANIFEST}'))['dev_trees']))
"
}

@test "regen_dev_trees --check succeeds on the checked-in tree" {
  run python3 "${REPO_ROOT}/${GENERATOR}" --check
  [[ "$status" -eq 0 ]] || {
    echo "generator reports drift (exit $status):"
    echo "$output"
    echo ""
    echo "Fix: run scripts/regen.sh and commit the result."
    return 1
  }
}

@test "cog markers are present in every generated surface (canary)" {
  # Without the markers the generator raises instead of silently passing,
  # but pin them anyway so a refactor that strips one fails here with a
  # clearer diagnostic than a regex miss.
  local -a surfaces=(
    "install.sh:dev_trees_install"
    "tests/run.sh:dev_trees_grep"
    "tests/bats/test_helper.bash:dev_trees_rsync"
    "scripts/regen_move_a1_enum.py:dev_trees_py"
  )
  local entry file marker
  for entry in "${surfaces[@]}"; do
    file="${entry%%:*}"
    marker="${entry##*:}"
    grep -qF "# [[[cog: ${marker} ]]]" "${REPO_ROOT}/${file}" || {
      echo "${file} is missing the '${marker}' cog open marker"
      return 1
    }
  done
}

@test "a manifest change is reported as drift in every consumer" {
  local work="${BATS_TEST_TMPDIR}/repo"
  mkdir -p "$work"
  cp -R "${REPO_ROOT}/manifests" "${REPO_ROOT}/scripts" "${REPO_ROOT}/install.sh" "$work/"
  mkdir -p "${work}/tests/bats"
  cp "${REPO_ROOT}/tests/run.sh" "${work}/tests/"
  cp "${REPO_ROOT}/tests/bats/test_helper.bash" "${work}/tests/bats/"

  printf '  - .mypy_cache\n' >>"${work}/${MANIFEST}"

  run python3 "${work}/${GENERATOR}" --check \
    --manifest "${work}/${MANIFEST}" \
    --install "${work}/install.sh" \
    --runsh "${work}/tests/run.sh" \
    --helper "${work}/tests/bats/test_helper.bash" \
    --move-a1 "${work}/scripts/regen_move_a1_enum.py"

  [[ "$status" -eq 5 ]] || {
    echo "expected drift exit 5, got $status"
    return 1
  }
  # The hint string is asserted by test_manifest_drift_localization.bats too;
  # keep both in step if it ever changes.
  [[ "$output" == *"Run scripts/regen.sh to regenerate"* ]]
  local file
  for file in install.sh tests/run.sh test_helper.bash regen_move_a1_enum.py; do
    [[ "$output" == *"$file"* ]] || {
      echo "drift diff did not name $file"
      return 1
    }
  done
}

@test "a malformed manifest exits 3, not a partial rewrite" {
  local work="${BATS_TEST_TMPDIR}/bad"
  mkdir -p "$work"
  printf 'dev_trees: []\n' >"${work}/dev-trees.yaml"

  run python3 "${REPO_ROOT}/${GENERATOR}" --check --manifest "${work}/dev-trees.yaml"
  [[ "$status" -eq 3 ]] || {
    echo "expected manifest-error exit 3, got $status"
    return 1
  }
}

@test "every consumer carries every dev-tree name" {
  # The assertion the manifest exists to make. Each consumer spells the names
  # differently, so match on the bare name within its generated block.
  local name
  while read -r name; do
    [[ -n "$name" ]] || continue

    # Pad the array line so the first and last entries match the same way
    # the middle ones do.
    local install_names
    install_names=" $(grep -F 'CURSOR_INSTALL_SKIP_NAMES=(' "${REPO_ROOT}/install.sh" |
      sed 's/.*(//; s/)$//') "
    [[ "$install_names" == *" ${name} "* ]] || {
      echo "install.sh CURSOR_INSTALL_SKIP_NAMES is missing '${name}'"
      return 1
    }

    grep -qF -- "--exclude-dir=${name}" "${REPO_ROOT}/tests/run.sh" || {
      echo "tests/run.sh cap-grep is missing '--exclude-dir=${name}'"
      return 1
    }

    # Fixed-string, both candidate forms: a regex would let '.' match any
    # character, so '.worktrees' would be satisfied by the 'worktrees/' line.
    grep -qF -- "--exclude='${name}'" "${REPO_ROOT}/tests/bats/test_helper.bash" ||
      grep -qF -- "--exclude='${name}/'" "${REPO_ROOT}/tests/bats/test_helper.bash" || {
      echo "test_helper.bash copy_skill_tree is missing an exclude for '${name}'"
      return 1
    }

    grep -qF "\"${name}\"," "${REPO_ROOT}/scripts/regen_move_a1_enum.py" || {
      echo "regen_move_a1_enum.py _GREP_EXCLUDES is missing '${name}'"
      return 1
    }
  done < <(dev_tree_names)
}

@test "the rsync exclude for .git stays bare so it also matches a gitdir file" {
  # A trailing slash restricts an rsync pattern to directories. In a git
  # worktree .git is a *file* pointing at the real gitdir, and letting that
  # leak into a fixture makes `git init` there behave unexpectedly.
  grep -qF -- "--exclude='.git'" "${REPO_ROOT}/tests/bats/test_helper.bash" || {
    echo "test_helper.bash must exclude '.git' without a trailing slash"
    return 1
  }
}

@test "top-level dev trees are skipped before cp -al, not pruned after" {
  # final contents cannot prove the tree was skipped before copying.
  local fakehome="${BATS_TEST_TMPDIR}/home"
  local src="${BATS_TEST_TMPDIR}/skill"
  copy_skill_tree "$src"

  src="$(cd "$src" && pwd -P)"
  mkdir -p "${src}/.venv/deep"
  : >"${src}/.venv/deep/marker"
  local cp_log="${BATS_TEST_TMPDIR}/cp-args" real_cp
  real_cp="$(command -v cp)"
  stub_cmd cp "printf '%s\\n' \"\$@\" >> '$cp_log'
exec '$real_cp' \"\$@\""

  HOME="${fakehome}" run "${src}/install.sh" --cursor
  [[ "$status" -eq 0 ]]

  local target="${fakehome}/.cursor/skills/pr-review-loop"
  [[ -f "${target}/SKILL.md" ]]
  [[ ! -e "${target}/.venv" ]]
  grep -Fxq -- "${src}/SKILL.md" "$cp_log"
  if grep -Fxq -- "${src}/.venv" "$cp_log"; then
    echo "cp received an excluded source directory"
    return 1
  fi
}
