# mid-iteration resume

the executable decision lives in `scripts/pr_loop_state.py resume-decision`.
`fetch_pr.sh` calls it for unfinished state before any checkout changes,
using the current local HEAD and the fetched remote head. resume requires the
recorded branch and never checks out or pulls. it fetches the pr head for validation
and refreshes the base ref. fetch exits 12, 13,
and 14 map to `EXTERNAL_PUSH`, `MAX_ITERATIONS`, and `SCOPE_SPLIT_RECOMMENDED`;
exit 8 maps to `SETUP_ERROR`.

## dispatch

`fetch_pr.sh` invokes this interface internally and prints `next iteration` on
a successful resume. Step 3.6 consumes that result; do not reconstruct the remote
head from `FETCH_HEAD`, which the subsequent base fetch overwrites.

```bash
python3 "$SKILL_ROOT/scripts/pr_loop_state.py" resume-decision \
  --state "$(git rev-parse --git-dir)/pr-loop/state.json" \
  --current-head "$CURRENT_HEAD" --remote-head "$REMOTE_HEAD"
```

pass `--dirty` when `git status --porcelain` is non-empty. output is
`{terminal_status, reason, next_iteration}`; only a null terminal status permits
resume. malformed state exits 2 and maps to `SETUP_ERROR`.

- empty history requires both heads to equal `initial_head_sha`; start iteration 1.
- completed history requires both heads to equal the latest `head_sha_after`;
  start the next completed iteration number.
- dirty checkout, a rewind to `head_sha_before`, and unrecorded local or remote
  commits return `EXTERNAL_PUSH`. the loop does not infer who made those changes.
- a recorded scope abort returns `SCOPE_SPLIT_RECOMMENDED`; otherwise exhausted
  iteration budget returns `MAX_ITERATIONS` before another review.

checkout safety runs before scope and budget decisions. completed state is
reinitialized by `state_init.sh`; state for another pr refuses setup. an unfinished
scope decision still follows [the scope rules](pr-scope.md).

## interrupted work

history records completed iterations only. an interrupted commit or push cannot
be recovered from the preceding entry's `head_sha_before`. preserve the checkout
and state for inspection instead of replaying work from that commit.

a reply posted before the atomic history append leaves the old comment baseline.
resume replays that disposition safely through the marker-aware helper. an
unrecorded push still fails the head check above. do not guess or reset. see
[`comment-handling.md#interruption-safety`](comment-handling.md#interruption-safety).

resume uses persisted `dry_run`; omitting the invocation flag cannot turn a dry
run into a normal run. absent fields keep their existing legacy defaults.
