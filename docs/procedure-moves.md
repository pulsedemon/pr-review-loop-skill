# Procedure moves (Move C: cross-doc consistency)

Four named moves applied by specific personas on every iteration.

Move A (test-intent audit) and Move B (second-instance sweep) intentionally live in each persona's prompt file: their wording is tuned per persona (`error_handling` uses bare-except examples, `blind_spots` uses inline-JSON `finding_evidence` and concurrency-hazard pattern names, etc.). Extracting them would either lose the per-domain pedagogy or require a per-persona override layer that defeats the deduplication purpose.

Only Move C, whose wording is identical across the `move_c: true` personas (declared in `reviewers/personas.yaml`), lives here as canonical text.

## Move C — cross-doc consistency (mandatory when diff touches both a doc and a spec)

When the diff touches both:

- a **doc**: README, AGENTS.md, anything under `docs/`, contributor-facing prose
- a **spec**: SKILL.md, files under `templates/` (schema files), files under `reviewers/` (persona schemas), CLAUDE.md

For contract drift (step 2) only, when the diff holds both a doc and the code that implements a contract the doc states, that code also counts as the spec: a command's documented flags and the parser that accepts them. Terminology drift (step 1) and the partial-diff rule below stay limited to the spec files above.

Do this:

1. **Terminology drift.** Identify each claim in the doc that paraphrases or summarizes a rule from the spec. Compare to the actual spec wording or behavior. If the doc misrepresents the spec, raise `severity: blocker, scope: in_scope` on the doc line. Cite both sides in `detail`.
2. **Contract drift.** Even when both sides use the same terminology, check whether they agree on what is *enforced*, *consumed*, or *required*. Patterns:
   - Doc lists a set of values (buckets, enum members, error codes, label types, sections, fields) that the code only partially consumes. → `suggestion` minimum; `blocker` if the doc is the contract callers rely on (a labeling protocol, a schema description, a SKILL.md behavior rule).
   - Spec/schema documents a constraint (cap, required field, mutual exclusion, exhaustive enum) that the actual schema doesn't express. Always `suggestion` here regardless of doc-as-contract status: `type_design` owns the blocker for this pattern (its reachability gate decides escalation). Cross-reference `type_design` in `detail` so synthesis can dedupe.
   - Doc claims a behavior the code does or doesn't implement (e.g. "the loader treats X as fatal" vs. code that ignores X). → `suggestion`; `blocker` if doc-as-contract.

If only one of {doc, spec} is in the diff but the other is referenced by name, read the unchanged file at HEAD and check the referenced section.

Out of scope: parallel drift where the doc and spec both describe the system incorrectly in the same way (correctness owns the underlying behavior).

### Applies to (`move_c: true` in `reviewers/personas.yaml`)

- `readability`
- `requirements`
- `comments`
- `blind_spots`

`adversary` also applies Move C, by inheritance of all four moves on its single per-iteration run; its prompt at `reviewers/adversary.md` carries its own pointer to this section. The manifest does not list adversary because the manifest drives the per-persona Move C extraction guard, not the inheritance contract.
