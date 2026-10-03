# Capability Index

This indexed canonical extension owns the supported public-surface inventory and
capability-specific contracts. Shared behavior remains owned by requirements and
architecture. The inventory contract is `evals/contracts/public-surfaces.json`;
`task docs:check` verifies its correspondence with authored skills and exports.

## Skills and Command Adapters

Each row names one portable skill and its OpenCode command adapter. Package-only
commands have a separate contract below.

| Skill | Command adapter |
| - | - |
| [agents-md](skills/agents-md.md) | [agents-md](commands/agents-md.md) |
| [asd-ste100](skills/asd-ste100.md) | [asd-ste100](commands/asd-ste100.md) |
| [askme](skills/askme.md) | [askme](commands/askme.md) |
| [ast-grep](skills/ast-grep.md) | [ast-grep](commands/ast-grep.md) |
| [briefing](skills/briefing.md) | [briefing](commands/briefing.md) |
| [code-explain](skills/code-explain.md) | [code-explain](commands/code-explain.md) |
| [code-review](skills/code-review.md) | [code-review](commands/code-review.md) |
| [commit-msg](skills/commit-msg.md) | [commit-msg](commands/commit-msg.md) |
| [docs-prepare](skills/docs-prepare.md) | [docs-prepare](commands/docs-prepare.md) |
| [docs-review](skills/docs-review.md) | [docs-review](commands/docs-review.md) |
| [eli5](skills/eli5.md) | [eli5](commands/eli5.md) |
| [goal](skills/goal.md) | [goal](commands/goal.md) |
| [humanize](skills/humanize.md) | [humanize](commands/humanize.md) |
| [mattermost](skills/mattermost.md) | [mattermost](commands/mattermost.md) |
| [mattermost-triage](skills/mattermost-triage.md) | [mattermost-triage](commands/mattermost-triage.md) |
| [mr-prepare](skills/mr-prepare.md) | [mr-prepare](commands/mr-prepare.md) |
| [release-prepare](skills/release-prepare.md) | [release-prepare](commands/release-prepare.md) |
| [release-review](skills/release-review.md) | [release-review](commands/release-review.md) |
| [rtk](skills/rtk.md) | [rtk](commands/rtk.md) |
| [skill-doctor](skills/skill-doctor.md) | [skill-doctor](commands/skill-doctor.md) |
| [slides-prompts-prepare](skills/slides-prompts-prepare.md) | [slides-prompts-prepare](commands/slides-prompts-prepare.md) |
| [spec-manage](skills/spec-manage.md) | [spec-manage](commands/spec-manage.md) |
| [stopit](skills/stopit.md) | [stopit](commands/stopit.md) |
| [task-prepare](skills/task-prepare.md) | [task-prepare](commands/task-prepare.md) |
| [task-review](skills/task-review.md) | [task-review](commands/task-review.md) |
| [task-triage](skills/task-triage.md) | [task-triage](commands/task-triage.md) |
| [taskmatic](skills/taskmatic.md) | [taskmatic](commands/taskmatic.md) |
| [team-1on1](skills/team-1on1.md) | [team-1on1](commands/team-1on1.md) |
| [team-agreements](skills/team-agreements.md) | [team-agreements](commands/team-agreements.md) |
| [team-feedback](skills/team-feedback.md) | [team-feedback](commands/team-feedback.md) |
| [team-health](skills/team-health.md) | [team-health](commands/team-health.md) |
| [team-incident](skills/team-incident.md) | [team-incident](commands/team-incident.md) |
| [team-onboarding](skills/team-onboarding.md) | [team-onboarding](commands/team-onboarding.md) |
| [team-people](skills/team-people.md) | [team-people](commands/team-people.md) |
| [team-performance](skills/team-performance.md) | [team-performance](commands/team-performance.md) |
| [team-report](skills/team-report.md) | [team-report](commands/team-report.md) |
| [team-retro](skills/team-retro.md) | [team-retro](commands/team-retro.md) |
| [team-roadmap](skills/team-roadmap.md) | [team-roadmap](commands/team-roadmap.md) |
| [team-sprint-close](skills/team-sprint-close.md) | [team-sprint-close](commands/team-sprint-close.md) |
| [team-sprint-start](skills/team-sprint-start.md) | [team-sprint-start](commands/team-sprint-start.md) |

## Agents, Plugins, and Package Surfaces

- Agents: [manager](agents/manager.md), [architect](agents/architect.md),
  [mapper](agents/mapper.md), [worker](agents/worker.md), [review](agents/review.md),
  and [critic](agents/critic.md).
- Selectable plugins: [rules-injector](plugins/rules-injector.md), [rtk](plugins/rtk.md),
  and [zed-bell](plugins/zed-bell.md).
- Standalone application: [memomatic](applications/memomatic.md) (MCP and CLI).
- Package tool: [route](package-tools/route.md).
- Package command: [rtk-stats](commands/rtk-stats.md).
- Administration: [scenario-oriented CLI](../requirements/interfaces/README.md#req-i-421---expose-scenario-oriented-integration-administration)
  and [application configuration](package-tools/config-setup.md). Withdrawn tools
  remain historical records, not supported CLI entrypoints.
