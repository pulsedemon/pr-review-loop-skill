# Human comments addendum

Shared by all panel reviewers. Each reviewer file links here from its own `## Human comments addendum` section.

You will also receive `human_comments`: discussion already on this PR. Treat these as additional context, not as blockers in themselves. Apply your normal scope-discipline rules.

When a human comment aligns with a finding you would raise anyway, prefer the human's phrasing and cite them in `detail` (e.g. `detail: "...raised by @alice in https://github.com/owner/repo/pull/N#discussion_rXXX"`). Do not put `@mentions` in `summary`, since `summary` is round-tripped into the Step 5 PR comment.

For an `out_of_scope` finding, `detail` is optional per `reviewers/output.schema.json` but still the right place to cite a human comment; do not put cites in `summary`.

PR-author comments are tagged `is_pr_author: true`; weigh them as intent clarification, not as approval. A PR-author comment requesting changes against their own PR is still intent clarification, not a blocker — the human is steering, not voting.
