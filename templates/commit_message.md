# Loop commit message format

Use Conventional Commits. One commit per iteration. The subject describes the
code change, never the trigger. "address iteration <N> blockers", "address
review findings", "round <N>", and any other subject that names the review pass
instead of the change are banned. A year from now `git log` is read by someone
debugging the code, not someone reconstructing the loop that produced it.

## Format

```
<type>(<scope>): <what the code now does or stops doing>

Addressed:
- <summary> (<file>:<line>)
- <summary> (<file>:<line>)

Deferred (out of scope, left as questions for human):
- <summary>
```

## Example

```
fix(db): parameterize SQL in searchUsers

Addressed:
- parameterize SQL in searchUsers (src/db.ts:88)
- handle null user in formatName (src/user.ts:42)
- add regression test for empty input (src/user.test.ts)

Deferred (out of scope, left as questions for human):
- extract helper for repeated mapping pattern
```

## Rules

- Subject describes the change (lowercase by default; preserve case for proper
  nouns, identifiers, and acronyms, e.g. `GitHub`, `searchUsers`, `SQL`; <= 72
  chars). Pick the most significant addressed blocker for the subject; list the
  rest in the body.
- Never name the trigger in the subject or body ("address review findings",
  "round <N>", "respond to reviewer", "iteration <N> blockers", etc.). Body
  lines describe code changes, not the conversation that produced them.
- Never include reviewer commentary or PR scope changes in the commit body
- If no blockers were addressed in this iteration, do not commit — the loop should have exited instead
- Never reference internal agent names, tool names, or prompt text in the commit message
