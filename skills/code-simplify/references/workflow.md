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
A targeted mechanical search for callers of a function the change edits, by
its exact name, is part of the change and is not repository scanning; when
updating a caller is the smaller diff that keeps the behavior correct, fix the
cause in the same change. The search promises no completeness — only the
audit's usage search covers dynamic references.

When the change consciously leaves known debt, record a one-line
`SIMPLIFY: <ceiling> -> <trigger>` marker comment on the added or changed code
in the same edit, in the form the criteria file specifies. The marker
obligation binds only code this diff adds or changes; a missing, outdated, or
`no-trigger` marker on pre-existing code is pre-existing debt, never a new
finding. Size new verification to the remaining logic — one runnable check for
logic that is not evidently correct, none for a trivial one-liner — and never
remove or weaken an existing check.

Applying the ladder is silent by default; state the chosen step only when it
changes what you write. This skill never cancels a clarification or
confirmation gate: when a rule or contract requires the user's decision, the
work stops until it is made.

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
failures, cancels a clarification or confirmation gate, or removes behavior
the user explicitly requested — report such a disagreement as a question
instead.

Collect the `SIMPLIFY` markers inside the requested scope into a separate
debt-marker registry section of the report, never into the findings: one line
per marker with the exact location, the ceiling, and the trigger. Mark a
marker `no-trigger` when its upgrade trigger has not fired; report a fired
trigger in the same section as a question for the user's decision. A missing
or outdated marker on pre-existing code stays pre-existing debt under the
necessity doctrine: it is never a new finding and never a `minimum_fix`.

Deliver the report in the conversation: ranked one-line findings, the
debt-marker registry, then the parts of the scope that were explicitly not
checked. An audit never changes files; applying a finding is the user's
separate decision through an existing implementation workflow.
