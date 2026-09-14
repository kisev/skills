# Workflow

This skill has the fixed `retro` entrypoint. Do not combine it with roadmap
editing, slide-image generation, task creation, or external publication.

Resolve the profile and handle setup or remembered updates through
`references/team-profile-workflow.md`. Run
`scripts/team_workflow.py action-check` first and read the resolved profile.

## 1. Establish Scope

Determine the exact retrospective outcome and period. Use the artifact format,
cadence, required sections, repository conventions, and team-specific rules from
`actions.retro`. If the request does not identify a period and it cannot be
derived unambiguously from the cadence and existing artifact, ask one question.

Express every period as strict UTC `[since, until)`. Convert an inclusive end
date to the next exclusive boundary. Never use `23:59:59`; fractional seconds
would be lost.

## 2. Build the Evidence Inventory

Use every profile project where `include` is true. Grouping or parallelism may
follow `category`, but neither optimization nor an empty result permits skipping
a configured project. Classify an author as internal or external only by the
profile's active membership, groups, effective dates, and
`external_contributors` policy.

Use only declared `sources`, `baseline.references`, and user-provided evidence.
Resolve connector commands from installed tool help or a dedicated connector
skill instead of inventing flags. Collection is read-only.

For a GitLab source with `actions.retro.use_gitlab_metrics: true`, run the
bundled collector with one `--project ID=path` argument for every included
GitLab project:

```shell
python3 scripts/gitlab_period_metrics.py \
  --hostname HOSTNAME \
  --since START_INCLUSIVE \
  --until END_EXCLUSIVE \
  --project ID=PROJECT_PATH \
  --output METRICS_ROOT/gitlab-period-metrics.json
```

Create a unique private temporary `METRICS_ROOT` for every run. Do not reuse
another run's output. The collector reads GitLab through `glab`, paginates,
deduplicates, and returns exit code `2` for partial evidence.

Verify all of the following before calling the evidence complete:

- Top-level and per-project `complete` values are true.
- Top-level, project, and source `errors` are empty.
- Every included profile project appears exactly once.
- `period.semantics` is `[since, until)` and boundaries match the request.
- Every event exposes `event_at` and `time_source`.
- Required delivery signals from the profile have a corresponding source.

Retry only the failed bounded source when safe. If a gap remains, report the
affected project, signal, and consequence; mark totals partial instead of
silently extrapolating.

## 3. Interpret Delivery Correctly

Do not present `merged`, `tagged`, and `shipped` as synonyms. Use each delivery
signal's configured state and timestamp. A release uses `released_at`. A tag
uses `tag.created_at` when available; `commit.created_at proxy` is only a proxy
and must be labelled as such.

For semantic versions:

- `X.0.0` is major, `X.Y.0` with `Y > 0` is minor, and `X.Y.Z` with `Z > 0` is patch.
- Treat aliases such as `v4.1` and `v4.1.0` as one release.
- Mark suffixes such as `-dev`, `-beta`, or `-auto-deploy` as pre-release.
- Do not count movable aliases such as `latest` or `stable` as releases.

Use merge-request title, description, author, and URL to explain significant
work as "outcome - purpose". Version-only bumps and mechanical updates may
contribute to totals but are not achievements without evidence of user or
engineering value. Never invent missing impact, plans, versions, or ownership.

## 4. Design the Retrospective

Follow `actions.retro.required_sections` and `actions.retro.rules`. A useful
delivery retrospective normally covers scope, evidence completeness, totals,
outcomes, project detail, unplanned work, contributors, risks or dependencies,
and next-period plans. Plans must come from current goals, roadmap evidence, or
an explicit user statement.

Create a dedicated project section only when the evidence supports it. Use
`project_detail_threshold` when configured; otherwise group smaller changes
without losing attribution. Order project sections by meaningful change volume,
not profile order. Do not duplicate one outcome across summary and project
sections unless the summary is explicitly an aggregate.

Credit team work accurately. Thank external contributors separately when the
profile policy and evidence identify them. Do not expose private member details
that are irrelevant to the artifact.

## 5. Render the Configured Artifact

Use `actions.retro.output.format` and `target_pattern`. For Marp output, include
valid front matter and keep background assets sequential and gap-free:

```yaml
---
marp: true
html: true
theme: configured-theme
size: 16:9
paginate: true
---
```

Keep each slide focused, reserve readable space for text, and express bullets as
"outcome - purpose". The exact title, theme, section order, links, and closing
content come from the profile or current repository evidence, not this public
skill.

Prepare the complete artifact in a private preview. Use `artifact-prepare`, show
the compact summary and conflicts, obtain confirmation, then run the returned
digest-bound `artifact-apply`. Do not modify image files and do not publish.

## 6. Verify and Report

Run the profile's `verification_command` when present and applicable. If it is
missing or stale, inspect repository-native build help and ask before choosing a
different command. Fix artifact errors and rerun verification.

Report the artifact path, period, projects covered, evidence completeness,
totals, external contributors, checks run, and every remaining limitation.
Delete or retain private temporary evidence according to the user's instruction;
never commit it by default.

Read `references/interaction-contract.md` for evidence and confirmation rules
and `references/language-policy.md` for user-facing prose.
