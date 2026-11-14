#!/usr/bin/env bats

# Pins the prose that bounds reviewer runtime: the tests persona's cap on
# test-runner starts, and the orchestrator's reviewer budget with its per-host
# recipes. A host LLM follows these sentences, so losing one silently brings
# back the unbounded behavior.

load test_helper

# Print one `## <heading>` section of a repo file, up to the next `## `. Fails
# when the heading is missing, so a renamed section fails every test that reads
# it instead of passing on an empty body.
_md_section() {
  awk -v want="## $2" '
    $0 == want { found = 1; next }
    found && /^## / { exit }
    found { print }
    END { exit !found }
  ' "${REPO_ROOT}/$1" || {
    echo "$1 has no '## $2' section" >&2
    return 1
  }
}

_require() {
  local body="$1" phrase="$2" why="$3"
  grep -qF -- "$phrase" <<<"$body" || {
    echo "missing: $phrase"
    echo "  $why"
    return 1
  }
}

@test "tests.md scopes mutation probes to the PR diff" {
  local body
  body=$(_md_section reviewers/tests.md 'Mutation probes') || return 1
  _require "$body" \
    'Mutate only lines the PR diff adds or changes, or code that a test the diff adds or changes names or asserts on' \
    'without it probes reach code the PR never touched'
}

@test "tests.md caps runner starts per review" {
  local body
  body=$(_md_section reviewers/tests.md 'Mutation probes') || return 1
  _require "$body" 'Start the test runner at most 8 times per review' \
    'the cap is what keeps a tests round from running for most of an hour'
  _require "$body" \
    'probe or not, in the checkout or on a copy, including each pass of a loop or script' \
    'baselines, sweeps and scripted loops would escape the count'
  _require "$body" 'A rerun the dispatch asks for counts toward the 8' \
    'a brief that asks for repeated runs would add runs past the cap'
  _require "$body" 'Add no stability reruns of your own and start no load generators' \
    'self-started flake reruns and CPU burners would add runs past the cap'
}

@test "tests.md limits each run to one test file" {
  local body
  body=$(_md_section reviewers/tests.md 'Mutation probes') || return 1
  _require "$body" 'Each run covers one test file' \
    'a probe could be widened to every test file that touches the code'
  _require "$body" \
    'For a probe, that is the file holding the test you expect to catch the mutation' \
    'without it nothing names which file a probe runs'
}

@test "tests.md judges a probe only by a run that exercised the test" {
  local body
  body=$(_md_section reviewers/tests.md 'Mutation probes') || return 1
  _require "$body" 'A probe needs no baseline run' \
    'a baseline per probe halves the probes the cap allows'
  _require "$body" \
    'for a probe only a passing run is evidence, and only when its output shows the target test ran' \
    'a mutant that never loaded, or a filter that matched nothing, would read as a survivor'
  _require "$body" 'not that no test pins the code' \
    'one file cannot show that no other test catches the mutation'
}

@test "reviewer-orchestration.md sets the reviewer budget" {
  local body
  body=$(_md_section docs/reviewer-orchestration.md 'Reviewer budget') || return 1
  _require "$body" '30 minutes from its batch launch' \
    'without a budget one slow reviewer holds the iteration'
  _require "$body" 'A valid response already received counts' \
    'a reviewer that answered before the deadline would be recorded as timed out'
  _require "$body" 'Record the launch time (`date +%s`)' \
    'Codex and Cursor compute the time left from the launch time'
  _require "$body" 'with neither a validated response nor a recorded error is stopped where the host allows' \
    'an overrun reviewer would keep running, and an errored one would be recorded twice'
  _require "$body" 'recorded in `reviewer_errors` as' \
    'the overrun must land in reviewer_errors so the iteration reads as incomplete'
  _require "$body" '"error": "timed out"' \
    'the error must say why the reviewer has no response'
  _require "$body" 'A resend requested for malformed output stays inside the same budget' \
    'a resend would restart the clock'
  _require "$body" 'Anything an overrun reviewer sends later is discarded' \
    'a late answer would earn a receipt after its error was recorded'
  _require "$body" 'Neither a relaunch nor a message to a stopped reviewer recovers a timeout' \
    'relaunching would double the wait the budget bounds'
  _require "$body" 'handled like any other reviewer error' \
    'the timeout would have no defined consequence'
}

@test "reviewer-orchestration.md says how each host keeps the budget" {
  local body
  body=$(_md_section docs/reviewer-orchestration.md 'Reviewer budget') || return 1
  _require "$body" 'never pass `run_in_background: false`' \
    'a foreground batch cannot be interrupted by the timer'
  _require "$body" 'also start `sleep 1800` as a background Bash command with `timeout: 1860000`' \
    'without a timer nothing fires at the budget, and a lower host limit would end it early'
  _require "$body" 'If that timer finishes on its own first, `TaskStop` each reviewer' \
    'the timer would fire and nothing would stop the reviewers, or a stopped timer would read as the budget'
  _require "$body" 'has a validated response or a recorded error, `TaskStop` the timer' \
    'a leftover timer exits later and reads as a timeout'
  _require "$body" 'call `wait_agent` in waits of at most 60000 ms' \
    'Codex would wait on reviewers with no deadline'
  _require "$body" '`interrupt_agent` each one still running' \
    'Codex would leave overrun reviewers running'
  _require "$body" 'launch each reviewer with `run_in_background: true`' \
    'a foreground Cursor launch blocks with no deadline'
  _require "$body" '`Await` each with `block_until_ms` set to the time left' \
    'Cursor would wait on reviewers with no deadline'
  _require "$body" 'abandoned, not stopped' \
    'Cursor has no cancel call, and the doc would imply one'
  _require "$body" 'the stop cannot be enforced there' \
    'the doc would imply a bound opencode cannot keep'
}
