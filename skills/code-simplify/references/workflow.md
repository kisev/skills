# Prevention and audit

Apply `references/simplification-criteria.md` on every invocation. This skill
is report-only for repositories: it never edits, deletes, moves, or reformats
project files, and it never launches an implementation.

## Passive prevention

While writing or changing code, apply the prevention ladder from
`references/simplification-criteria.md` — necessity, existing code, standard
library, native platform, installed dependency, one line, minimum — to the
current change, and stop at the first step that satisfies the agreed need. The
ladder applies to code being written or changed only: no repository scanning,
no unrelated files, no review of other people's code, and no task expansion.
Applying it is silent by default; state the chosen step only when it changes
what you write.

Text simplification never activates this skill: prose belongs to `asd-ste100`,
`humanize`, and `eli5`. A specification audit routes to `spec-manage`, and a
merge-request review routes to `code-review`.

## Explicit audit

Run an audit only on an explicit user request, inside the explicitly requested
or agreed scope; when the scope is ambiguous, ask one short question before
reading anything. Follow the audit contract in
`references/simplification-criteria.md`: findings ranked by expected benefit,
one line each, every finding carrying the exact location, exactly one tag of
`delete`, `stdlib`, `native`, `reuse`, `yagni`, or `shrink`, and the concrete
simpler alternative that preserves behavior. A candidate without a usable
alternative is not reported.

Perform the usage search, including dynamic references, before any `delete`
finding; an unresolved dynamic reference blocks it. Apply the safety floor:
never propose a simplification that crosses or weakens a trust boundary, risks
data loss, weakens security or accessibility, drops error handling that hides
failures, or removes behavior the user explicitly requested — report such a
disagreement as a question instead.

Deliver the report in the conversation: ranked one-line findings, then the
parts of the scope that were explicitly not checked. An audit never changes
files; applying a finding is the user's separate decision through an existing
implementation workflow.
