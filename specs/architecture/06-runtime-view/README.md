# Runtime View

Shared read-only and mutating lifecycles follow
[Interaction and Confirmation](../08-crosscutting-concepts/interaction-confirmation.md).
The `goal` path researches available facts, normalizes a `work-item/v1`
internally, optionally performs one independent premortem, and presents at most
4000 characters of structured Markdown without executing or persisting the goal.
Storage-neutral task preparation and review normalize one supported source and
present chat output by default. GitLab task preparation may render a bounded
manual publication plan. Task triage resolves one issue or a bounded issue
collection, stores private content-addressed evidence and analysis in XDG state,
reuses current per-issue analysis, and atomically updates stable Markdown views.
It composes the task-review quality contract and emits manual commands but never
executes them or mutates GitLab.

The three task workflows materialize one tracker-neutral release-planning
validator. Task triage owns GitLab release and milestone evidence and persistent
planning decisions. Task review validates the same sidecar without owning state.
Task preparation consumes a current accepted decision or requests scoped
single-item triage; it does not duplicate release-policy interpretation.

Routing resolves host inventory, creates a receipt, consumes it once for a
matching Task, validates the structured result, and expires the receipt.
Installation and reconciliation validate ownership and digests before
publishing or archiving package assets. Reconcile ignores portable skill trees
and installer lock files; their update and removal lifecycle belongs to the
`skills` CLI.

Portable installation resolves the Pages well-known index, verifies an archive
SHA-256 digest, extracts root `SKILL.md` plus local resources, and records the
Pages source for later updates. No build command runs on the user's machine.

Specification writing validates the complete candidate snapshot after bounded
writes. Updates additionally compare it with an explicitly retained complete
baseline; initialization and onboarding report lifecycle as `not_checked`.
Audits bind a bounded evidence snapshot, treat formal results as structural
evidence, split drift into atomic claims or boundaries, and classify each unit
by one ordered decision table. Full audits give the same snapshot, without
primary conclusions, to one independent critic; focused audits do so only when
requested. The report keeps formal validation, quality, drift, unchecked
boundaries, critic dispositions, and aggregate status separate. Mandatory
incompleteness takes aggregate precedence without hiding confirmed findings.

Specification routing first preserves an explicit mode and scope or derives a
mode from user intent. Before choosing initialization or onboarding it inspects
source, tests, schemas, configuration, CI, and deployment. If multiple modes
remain possible, it asks one bounded question and performs no write; read-only
intent cannot enter a writing lifecycle.

Code-review's skill-owned `review_workflow.py` coordinates collection, independent
review, finalization, and plan creation using shared GitLab primitives. Its separate
`review_publication.py` implements the one-action lifecycle owned by
[the code-review requirement](../../capabilities/skills/code-review.md). Preparation
never starts that lifecycle. Manual local patches remain a separate operation.
