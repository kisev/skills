# Workflow

This skill has the fixed `sprint-close` entrypoint. Do not accept a public action or
mode selector or combine actions. Apply `humanize` to drafted closing report
prose. Resolve the default private profile, explicit
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

Every closing artifact ends with a "Data sources" section in the artifact's
language: one row per contributing source with the kind, the exact location
(URL or path), the collected `[since, until)` window or point timestamp,
completeness, and `collected_at`. Record contributing sources in the private
evidence store under
`${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/team-evidence/<profile>/` with
`scripts/evidence_store.py evidence-record --profile
PROFILE` (`--kind mattermost --location URL` for chats, `--kind file --location PATH` for protocols and planning documents); render the section
from `evidence-show --profile PROFILE --since START --until END`. When
GitLab delivery evidence is collected with the bundled metrics collector, pass
`--resume-profile PROFILE` so complete windows are reused from the store and
only the missing delta is fetched. After `artifact-write`, snapshot the
artifact with `artifact-record --profile PROFILE --target ARTIFACT_PATH --since START --until END --source KEY`. External publication is outside this
skill.
