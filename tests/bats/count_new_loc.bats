#!/usr/bin/env bats

load test_helper

setup() {
  make_tmp_repo
  # build a fake "origin" with a base branch so the script's BASE_REF logic resolves.
  git checkout -q -b feature
  echo "first" > a.txt
  git add a.txt
  git commit -q -m "first"
  # Simulate origin/main pointing at a parent commit
  git update-ref refs/remotes/origin/main "$(git rev-parse HEAD~0 2>/dev/null || git rev-parse HEAD)"
  # add lines on feature
  printf 'line1\nline2\nline3\n' > a.txt
  echo "lockcontent" > package-lock.json
  echo "src1" > src.js
  git add a.txt package-lock.json src.js
  git commit -q -m "feature changes"
}

@test "total LOC on line 1, included files in stdout, excluded in stderr" {
  run bash -c "${SCRIPTS}/count_new_loc.sh main 2>${BATS_TEST_TMPDIR}/err"
  [[ "$status" -eq 0 ]]
  # line 1 must be an integer
  first=$(echo "$output" | head -n1)
  [[ "$first" =~ ^[0-9]+$ ]]
  # included files appear as TSV rows after line 1: <added>\t<deleted>\t<path>
  rows=$(echo "$output" | tail -n +2)
  [[ -n "$rows" ]]
  echo "$rows" | grep -qE $'^[0-9]+\t[0-9]+\t.+$'
  echo "$rows" | grep -qE $'^[0-9]+\t[0-9]+\tsrc\\.js$'
  # included rows must not contain excluded paths
  run grep -q "package-lock.json" <<<"$rows"
  [[ "$status" -ne 0 ]]
  # excluded list should mention package-lock.json
  grep -q "excluded:" "${BATS_TEST_TMPDIR}/err"
  grep -q "package-lock.json" "${BATS_TEST_TMPDIR}/err"
}

@test "non-ASCII filenames are counted with their literal path (core.quotepath=false)" {
  make_tmp_repo "${BATS_TEST_TMPDIR}/unicode-repo"
  printf 'base\n' > base.txt
  git add base.txt
  git commit -q -m "base"
  git update-ref refs/remotes/origin/main "$(git rev-parse HEAD)"

  printf 'naïve café\n' > "café.ts"
  git add "café.ts"
  git commit -q -m "add unicode file"

  run bash -c "${SCRIPTS}/count_new_loc.sh main 2>${BATS_TEST_TMPDIR}/err"
  [[ "$status" -eq 0 ]]
  rows=$(echo "$output" | tail -n +2)
  # literal UTF-8 path present; not git's default octal-escaped/quoted form
  echo "$rows" | grep -qF $'\tcafé.ts'
  run grep -q '\\303' <<<"$rows"
  [[ "$status" -ne 0 ]]
}

@test "usage error returns exit 1" {
  run bash "${SCRIPTS}/count_new_loc.sh"
  [[ "$status" -eq 1 ]]
}

@test "missing base branch returns exit 2" {
  run bash "${SCRIPTS}/count_new_loc.sh" no-such-branch
  [[ "$status" -eq 2 ]]
}

@test "rename handling uses the post-rename path and still excludes lockfiles" {
  make_tmp_repo "${BATS_TEST_TMPDIR}/rename-repo"
  printf 'old line\n' > old.ts
  printf 'lock v1\n' > old-lock.json
  git add old.ts old-lock.json
  git commit -q -m "add old files"
  git update-ref refs/remotes/origin/main "$(git rev-parse HEAD)"

  git mv old.ts new.ts
  git mv old-lock.json package-lock.json
  printf 'old line\nnew line\n' > new.ts
  printf 'lock v2\n' > package-lock.json
  git add new.ts package-lock.json
  git commit -q -m "rename files"

  run bash -c "${SCRIPTS}/count_new_loc.sh main 2>${BATS_TEST_TMPDIR}/err"
  [[ "$status" -eq 0 ]]
  first=$(echo "$output" | head -n1)
  [[ "$first" =~ ^[0-9]+$ ]]
  rows=$(echo "$output" | tail -n +2)
  echo "$rows" | grep -q $'new\\.ts$'
  run grep -q "old.ts => new.ts" <<<"$rows"
  [[ "$status" -ne 0 ]]
  run grep -q "package-lock.json" <<<"$rows"
  [[ "$status" -ne 0 ]]
  grep -q "# excluded: package-lock.json" "${BATS_TEST_TMPDIR}/err"
}

@test "directory and binary exclusions stay off stdout and appear on stderr" {
  mkdir -p node_modules/foo assets
  printf 'module.exports = 1;\n' > node_modules/foo/index.js
  printf '\211PNG\r\n\032\n\000chunk' > assets/logo.png
  git add node_modules/foo/index.js assets/logo.png
  git commit -q -m "add excluded files"

  run bash -c "${SCRIPTS}/count_new_loc.sh main 2>${BATS_TEST_TMPDIR}/err"
  [[ "$status" -eq 0 ]]
  rows=$(echo "$output" | tail -n +2)

  run grep -q "node_modules/foo/index.js" <<<"$rows"
  [[ "$status" -ne 0 ]]
  run grep -q "assets/logo.png" <<<"$rows"
  [[ "$status" -ne 0 ]]

  grep -q "# excluded: node_modules/foo/index.js" "${BATS_TEST_TMPDIR}/err"
  grep -q "# excluded (binary): assets/logo.png" "${BATS_TEST_TMPDIR}/err"
}

@test "brace-form renames emit only the post-rename path and still exclude lockfiles" {
  make_tmp_repo "${BATS_TEST_TMPDIR}/brace-rename-repo"
  mkdir -p src/old/shared deps/old
  printf 'old line\n' > src/old/shared/value.ts
  printf 'lock v1\n' > deps/old/package-lock.json
  git add src/old/shared/value.ts deps/old/package-lock.json
  git commit -q -m "add old tree"
  git update-ref refs/remotes/origin/main "$(git rev-parse HEAD)"

  mkdir -p src/new/shared deps/new
  git mv src/old/shared/value.ts src/new/shared/value.ts
  git mv deps/old/package-lock.json deps/new/package-lock.json
  rmdir src/old/shared src/old deps/old
  printf 'old line\nnew line\n' > src/new/shared/value.ts
  printf 'lock v2\n' > deps/new/package-lock.json
  git add src/new/shared/value.ts deps/new/package-lock.json
  git commit -q -m "rename tree"

  run bash -c "${SCRIPTS}/count_new_loc.sh main 2>${BATS_TEST_TMPDIR}/err"
  [[ "$status" -eq 0 ]]
  rows=$(echo "$output" | tail -n +2)

  echo "$rows" | grep -q $'src/new/shared/value\\.ts$'
  run grep -q "{old => new}" <<<"$rows"
  [[ "$status" -ne 0 ]]
  run grep -q "deps/new/package-lock.json" <<<"$rows"
  [[ "$status" -ne 0 ]]

  grep -q "# excluded: deps/new/package-lock.json" "${BATS_TEST_TMPDIR}/err"
}
