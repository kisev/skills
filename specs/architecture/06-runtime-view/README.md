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
publishing or archiving. Reconcile treats the exact portable source marker as
future cleanup authorization, snapshots bounded local state, archives current
bytes, invokes the configured exact `skills remove` against the selected
OpenCode/Codex paths, and validates its bounded postconditions.

Portable installation resolves the Pages well-known index, verifies an archive
SHA-256 digest, extracts root `SKILL.md` plus local resources, and records the
Pages source for later updates. No build command runs on the user's machine.

Code review preparation collects complete GitLab evidence and label catalogs,
validates each actionable suggestion or unified patch against the exact reviewed
head, creates immutable body and patch files plus closed publication actions,
and atomically publishes a non-mutating plan. Each optional publication command
starts a separate lifecycle for exactly one action: confirm its digest, reload
the immutable plan, revalidate bounded files and live GitLab state, invoke `glab`
without a shell, verify the postcondition, and record an atomic receipt. A
definitive non-mutating rejection permits an evidence-bound retry; an uncertain
result remains partial and cannot be replayed. Review preparation never invokes
that helper, and no command applies a batch or edits the reviewed checkout.
