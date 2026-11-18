# Output addendum

Shared by every reviewer, including the adversary. Each reviewer file links here from its own `## Output` section.

Your whole reply is one JSON object: the first character is `{` and the last is `}`. Write no sentence before or after it and no code fence around it.

`reviewers/output.schema.json` rejects any key it does not list, at every level. These are the only keys:

- Top level: `reviewer`, `verdict`, `findings`, `evidence`
- Each finding: `severity`, `scope`, `file`, `line`, `summary`, `detail`, `suggested_fix`, `finding_evidence`, `move_b_pattern`, `move_a1_pattern`
- `evidence`: `files_read`, `symbols_traced`, `notes`
- `finding_evidence`: `file`, `line`, `symbol`, `snippet`

`summary` is a key of a finding. There is no top-level `summary`: an overall assessment has no field, so leave it out. A finding has one `line`; put a range in `detail`.
