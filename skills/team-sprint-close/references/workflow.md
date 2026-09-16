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

Read `references/interaction-contract.md`. Profile and context writes use their
confirmed prepare/save lifecycle because they modify user configuration.
Workspace roadmap, presentation, or prompt files are written directly through
`artifact-write` with bounded paths and atomic replacement. Do not modify the
workspace context file. Reject symlink and traversal targets.
External publication is outside this skill.
