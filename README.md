# Agent Skills

[Русский](README.ru.md)

Portable Agent Skills for repository engineering, documentation, GitLab work,
and OpenCode. Shared response-language, evidence, error, question,
confirmation, ownership, and work-item contracts are canonical in
`shared/references/` and materialized into portable skills. Each `skills/`
directory is independently installable.

## Quick Start

Install all skills for OpenCode:

```shell
npx --yes skills@1.5.23 add kisev/skills --agent opencode --skill '*' --copy --yes
```

The same pinned Git source is the public installation contract for Codex; replace
`--agent opencode` with `--agent codex`, or replace `'*'` with one skill name.
The pinned executable is `npx --yes skills@1.5.23`.

Use a GitHub tag for a reproducible installation:

```shell
npx --yes skills add https://github.com/kisev/skills/tree/v2.0.0 \
  --agent opencode --skill '*' --copy --yes
```

Install one skill by replacing `--skill '*'`:

```shell
npx --yes skills add kisev/skills --agent opencode \
  --skill spec-manage --copy --yes
```

`npx skills` installs to project scope by default; add `--global` when skills
must be available to every user project.

List without writing:

```shell
npx --yes skills add kisev/skills --list
```

## Repository Development

Install the pinned runtimes and standalone tools from the repository root:

```shell
mise install
```

`mise.toml` pins Python 3.12, Node.js 22, and standalone tools. Python check
dependencies are in `pyproject.toml` and `uv.lock`; portable runners still use
only the standard library. The separate npm package in `packages/opencode/` has
its own `package.json` and `package-lock.json`; there is no root npm workspace.

The single local and CI quality gate is:

```shell
task check
```

`task --list` shows available tasks. `task format` and the explicit source
materialization step change declared generated files; checks do not.
`task generate` first materializes the declared shared copies into the committed
`skills/<name>/` directories, then creates ignored `.build/skills`, the private
build-only `@kisev/skills` archive/index, and package staging. `task generate:check`
checks source parity and artifact reproducibility without writing
the worktree. `python3 scripts/build_skills.py --generate` is the explicit
committed-copy materialization command; do not edit generated shared references
by hand.

Install Git hooks with:

```shell
lefthook install
```

`pre-commit` invokes `task pre-commit`, selecting non-mutating checks by staged
paths. Markdown/data, Python/skills, and the OpenCode package are independent;
complete `task check`. Hooks neither format files nor add them to the index.

If a check cannot find an executable, run `mise install`, then `mise current`.
For an `uv.lock` error use `uv sync --locked`; changing the lock file is drift.
For generated drift, change the source in `shared/references/` or
`packages/opencode/src/registry.ts`, then run `task generate`; do not edit a
build artifact manually. [CONTRIBUTING.md](CONTRIBUTING.md) describes the full
check structure.

## Behavioral Evals

The canonical corpus is [`evals/`](evals/): versioned JSON Schemas, immutable
scenario ID/revision, and a SHA-256 digest. Offline validation is:

```shell
task eval:check
```

It validates schemas and corpus, then runs only the deterministic offline suite.
It requires neither OpenCode, Codex, network access, credentials, nor user
configuration.

The following is a trusted live evaluation, not offline validation. It has no
default model and runs only in a trusted environment with exact host, model, and
limits:

```shell
uv run --locked python scripts/eval_runner.py --trusted-live \
  --host opencode --model provider/exact-model --timeout 60 \
  --max-tokens 3000 --max-cost 2 --output evals/live/result.json
```

`evals/live/` is ignored by Git. The `Trusted live evaluations` workflow is
available only through manual `workflow_dispatch`, uses a protected environment,
and does not run for a pull request or fork.

## Skill Catalog

Skills are listed in [migration inventory](docs/migration-inventory.md). Shared
`work-item/v1` contracts are materialized into each affected portable skill.
Publication planning remains a local Markdown plan with `external_mutations=false`.

## Build Distribution

`task generate` builds a well-known index, SHA-256 lock, and self-contained
`.tar.gz` archive per skill. `SKILL.md` is at each archive root. The
`@kisev/skills` package is private and build-only; direct users install from the
Git source above, not from that package.

## OpenCode Integration

Install the optional integration separately:

```shell
npm install @kisev/skills-opencode@2.0.0
npm exec -- skills-opencode install --scope global --dry-run
```

Apply only the preview digest:

```shell
npm exec -- skills-opencode install --scope global --confirm <digest>
```

For scripts and the full machine-readable plan, add `--json`. Use
`--scope project` for the current repository; the installer then manages files
only under `.opencode/` and never creates or edits `opencode.json`.

Configure the plugin manually in `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@kisev/skills-opencode"]
}
```

Details are in [README package](packages/opencode/README.md).

Manage fixed-agent models and additional critics directly through the CLI without
LLM tokens:

```shell
npm exec -- skills-opencode agent list --scope global
npm exec -- skills-opencode agent configure manager --scope global --dry-run
npm exec -- skills-opencode critic add security --scope global \
  --model anthropic/claude-sonnet-4-6 --dry-run
```

Every mutation first creates a short plan and private one-time receipt with a
TTL. Apply it only with `--confirm <digest>`. `/agent-profiles` is the only
slash adapter for the `agent_profiles` package tool; direct CLI is also available.

## Compatibility and Requirements

- Portable skills require a host that supports Agent Skills.
- Runners use Python 3.12+ standard library only.
- The OpenCode package targets OpenCode `>=1.18.29 <1.19.0` and requires Node.js
  22+.
- `ast-grep` and `rtk` require their respective CLI to be installed already;
  skills do not install them.

GitLab skills use one canonical private collection by GitLab-object identity,
rather than by the calling skill name. Installed copies contain byte-identical
runtime, artifact schema, and workflow contract. Collection is limited to a
GET-only allowlist, exact SHA, and completeness; publication stays a local
Markdown plan with `external_mutations=false`.

## Runtime Limits

Stateful OpenCode plugins remain opt-in; portable skills work without package
assets. Background Attempts own a managed worktree and terminal reconciliation;
the plugin remains opt-in. The cron scheduler uses a strict evaluator and
machine-readable receipts, and both its definitions and plugin are disabled by
default. Mattermost does not yet have complete parity with its claimed scenarios,
and runtime state and `doctor` require further hardening.

The `background-attempts`, `schedule`, and `autonomy-policy` wrappers are
disabled by default. `goal` is not a wrapper and creates no state. OpenChamber
Goal Mode remains an external way to execute a goal; this project has no goal
lifecycle or auto-continuation.

## Update and Removal

```shell
npx --yes skills update --yes
```

```shell
npx --yes skills remove spec-manage --agent opencode --yes
```

`npx skills remove --all` affects every skill in the selected scope; removing
skills by name is safer for this set.

## Security and Limits

Skills that write show a preview and require confirmation. Confirmations are
grouped by independent risk and exact mutation boundary; external publication,
history rewrite, and destructive cleanup always need separate approvals. Do not
provide credentials in prompts, argv, or logs. See [SECURITY.md](SECURITY.md).
`task-triage`, `task-review`, and `task-prepare` are GitLab workflows with their
own explicitly scoped contracts.

```shell
npm exec -- skills-opencode uninstall --scope global --dry-run
npm exec -- skills-opencode uninstall --scope global --confirm <digest>
```

## Maintainers

```shell
python3 scripts/build_skills.py --check
python3 -m unittest discover -s tests -v
for skill in skills/*; do uvx --from skills-ref agentskills validate "$skill"; done
npx --yes skills add . --list
```

The repository is MIT-licensed. See [LICENSE](LICENSE).
Release history is in [CHANGELOG.md](CHANGELOG.md).
