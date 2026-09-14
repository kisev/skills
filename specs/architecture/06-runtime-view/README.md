# Runtime View

Shared read-only and mutating lifecycles follow
[Interaction and Confirmation](../08-crosscutting-concepts/interaction-confirmation.md).
The `goal` path researches available facts, normalizes a `work-item/v1`
internally, optionally performs one independent premortem, and presents at most
4000 characters of structured Markdown without executing or persisting the goal.
Storage-neutral task workflows normalize one supported source and then prepare,
review, or triage it; they present chat output by default and never publish.

Routing resolves host inventory, creates a receipt, consumes it once for a
matching Task, validates the structured result, and expires the receipt.
Installation and reconciliation validate ownership and digests before
publishing or archiving.

Portable installation resolves the Pages well-known index, verifies an archive
SHA-256 digest, extracts root `SKILL.md` plus local resources, and records the
Pages source for later updates. No build command runs on the user's machine.
