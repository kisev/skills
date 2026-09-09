# Workflow

This skill has the fixed `slides-prompts` entrypoint. Do not accept a public action or
mode selector, combine actions, or infer projects,
participants, cadence, or delivery signals from repository activity. Exactly one
explicit context is required: a read-only JSON file, a saved named context, or
chat facts.

First run `scripts/team_workflow.py action-check` with one source. If required
fields are missing, return `setup-required`, show the discovered values, and ask
only for missing fields through the host mechanism or in chat. General advance
setup, implicit defaults, and automatic discovery are forbidden.

Always state a period as `[since, until)`. For `planning`, prepare only scope;
`sprint-status` does not close the cycle; `sprint-close` does not perform
planning; `retro` does not change the roadmap; `roadmap` does not create a
presentation; `slides-prompts` does not change the presentation or images. Do
not present `merged`, `tagged`, and `shipped` as the same state.

Read `references/interaction-contract.md`. Writing context, roadmap,
presentation, or prompts follows `prepare -> present -> confirm -> apply ->
report`: `context-prepare` or `artifact-prepare` returns a compact summary,
content-addressed artifact path, SHA-256 digest, TTL, and ready apply command.
`context-save` or `artifact-apply --digest <SHA-256>` rechecks the digest,
expiration, one-time use, and path, then returns a separate report. Do not modify
the workspace context file. Reject symlink, traversal, tampered, and stale plans.
External publication is outside this skill.
