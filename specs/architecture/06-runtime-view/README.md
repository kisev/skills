# Runtime View

Read-only requests resolve scope, prepare evidence, present a structured result,
and report. Mutating requests resolve, prepare an exact plan, present it,
confirm, apply atomically, and report. Routing resolves host inventory, creates a
receipt, consumes it once for a matching Task, validates the structured result,
and expires the receipt. Installation and reconciliation validate ownership and
digests before publishing or archiving.
