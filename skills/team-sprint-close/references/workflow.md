# Workflow

This skill has the fixed `sprint-close` entrypoint. Do not accept a public action or
mode selector or combine actions. Resolve the default private profile, explicit
overrides, self-setup, and remembered updates through
`references/team-profile-workflow.md`. Do not infer projects, participants,
cadence, or delivery signals from unrelated repository activity.

First run `scripts/team_workflow.py action-check` without a context flag. If it
returns `setup-required`, inspect user-supplied sources and ask only for fields
that remain missing. An explicit profile or legacy context overrides the default.

Always state a period as `[since, until)`. For `planning`, prepare only scope;
`sprint-status` does not close the cycle; `sprint-close` does not perform
planning; `retro` does not change the roadmap; `roadmap` does not create a
presentation; `slides-prompts` does not change the presentation or images. Do
not present `merged`, `tagged`, and `shipped` as the same state.

Read `references/interaction-contract.md`. Writing profiles, context, roadmap,
presentation, or prompts follows `prepare -> present -> confirm -> apply ->
report`: `profile-prepare`, `context-prepare`, or `artifact-prepare` returns a compact summary,
content-addressed artifact path, SHA-256 digest, TTL, and ready apply command.
The matching save or apply command rechecks the digest,
expiration, one-time use, and path, then returns a separate report. Do not modify
the workspace context file. Reject symlink, traversal, tampered, and stale plans.
External publication is outside this skill.
