#!/usr/bin/env bats

load test_helper

setup() {
  make_tmp_repo
}

@test "exits 2 when sonar CLI is missing" {
  assert_sonar_exits_2_missing_cli "fetch_sonar.sh"
}

@test "exits 3 when sonar not authenticated" {
  assert_sonar_exits_3_not_authenticated "fetch_sonar.sh"
}

@test "exits 1 on usage error" {
  assert_sonar_exits_1_usage_error "fetch_sonar.sh"
}
