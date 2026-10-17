# Manage Portable Skills

[Русский](../ru/how-to/portable-skills.md)

Use this guide to install, update, rebind, clean up, or troubleshoot portable
skills. These operations are independent of `@kisev/agentomatic`.

## Choose a Scope and Host

| Choice | Option | Canonical location |
| - | - | - |
| Global scope | Add `--global` | `~/.agents/skills` |
| Project scope | Omit `--global` | `.agents/skills` |
| Every `.agents` host (default) | Omit `--agent` | One canonical copy in the selected scope |
| One host only | `--agent <name>` | Selected scope |

Omitting `--agent` lets the installer select every host that reads
`.agents/skills`, plus any other installed host.

## Install

Preview the npm installer version, run it, then list the skills actually
installed. `skills@latest` is the CLI version, not the Pages distribution
version. The tag can move between commands; npx does not install a global CLI.

Install skills globally:

```shell
# Registry version of the installer
npm view --prefer-online skills@latest version

# Install skills
npx --yes skills@latest add https://kisev.github.io/skills --global

# Installed skills, not the npm installer
npx --yes skills@latest list --global
```

Install skills in the current project:

```shell
# Registry version of the installer
npm view --prefer-online skills@latest version

# Install skills
npx --yes skills@latest add https://kisev.github.io/skills

# Installed skills in this project
npx --yes skills@latest list
```

The command opens a skill picker with every skill preselected; deselect what you
do not need. Inside an agent session it runs non-interactively and installs
everything, so pass `--skill <name>` to stay selective; exact names come from
the [skill catalog](../reference/skill-catalog.md). The default keeps one
canonical copy and links hosts with private skill directories to it; add
`--copy` only when your setup cannot follow symlinks. List the published
catalog without writing:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --list
```

The GitHub Pages URL is the supported moving stable-release channel. Its release
metadata identifies the release and source revision, while the Pages index binds
each archive to a SHA-256 digest. The current GitHub Release is available at
`https://github.com/kisev/skills/releases/latest`. The authored `skills/` tree is
intentionally not a public install source; `.agents/skills/project-release` is a
repository-local maintainer workflow.

### Install The Development Channel

Replace the stable source with the explicit `/dev` source:

```shell
# Registry version of the installer (still latest)
npm view --prefer-online skills@latest version

# Install the dev skill distribution
npx --yes skills@latest add https://kisev.github.io/skills/dev --global

# Installed skills
npx --yes skills@latest list --global
```

The moving dev channel updates after successful pushes to `dev`. Its technical
version identifies the workflow run and source revision; it does not predict the
next stable release. Repeat the stable `add` command to switch an installation
back to stable.

## Update

Update tracked global skills installed from Pages:

```shell
npx --yes skills@latest update --global
```

Omit `--global` for project scope. An installation created from a Git repository
or tag remains bound to that source. Repeat the matching `add` command with the
Pages URL and the same scope to rebind it.

`update` refreshes tracked skills, detects names deleted upstream, and offers to
remove their local copies. The removal offer appears only when `update` runs in
a terminal without its `--yes` flag; in non-interactive mode the CLI skips the
offer and keeps retired copies, so remove them explicitly instead. `update`
takes skill names, not source URLs, as positional arguments. OpenCode package
assets have a separate update lifecycle described in the
[OpenCode integration guide](opencode-integration.md#update).

## Check the Environment Contract

Every skill that needs an external tool carries a materialized
`references/requirements.json` in its installed directory. It records each tool
with its `check` command, a copy-ready `install` command, the pinned tool
version, and the distribution `source_revision`. Run the bundled stdlib check in
the first session and show its output. The first path below is the global scope,
the second the project scope:

```shell
python3 ~/.agents/skills/code-review/scripts/check_environment.py
python3 .agents/skills/code-review/scripts/check_environment.py
```

Each line is `OK` or `FAIL`, and a failure prints the exact repair command
instead of dead-ending. The runner installs nothing and makes no network call.
The manifest is stitched at build time and is deterministic: `task generate:check`
validates it, and the local channel check compares the manifest
`source_revision` with the Pages index and the workspace npm pin without the
registry. `agentomatic doctor` reads the installed manifests for the global and
project scopes and prints the same contract; without an installed manifest it
reports an honest "not found".

## Remove Retired Names

The current [migration inventory](../migration-inventory.md) defines thirteen
retired names. Normally, accept their removal when `skills update` reports them.
To remove them explicitly from a global installation, run:

```shell
npx --yes skills@latest remove attempt schedule usage overview project-spec skill-improver skill-improve walkthrough team-workflow summary doit lsp-report stopit --global --yes
```

To remove from one host only, add its `--agent <name>` option.

Use the same scope as the installation. Omit `--global` for project
scope. Avoid `remove --all` unless every portable skill in that scope should be
removed.

The OpenCode package never installs, updates, inspects, or removes portable
skills. Use `skills update` or `skills remove` for their complete lifecycle.

## Troubleshoot Discovery

List installed global skills:

```shell
npx --yes skills@latest list --global
```

For project scope, omit `--global`. If a newly installed skill is not visible,
check `~/.agents/skills` or `.agents/skills` and restart the host. After a release
renames a skill, repeat `add` for additions and remove retired names explicitly.

## Check Skill-Text Changes Under Pressure

Static checks and pins cannot prove that a skill text changes agent behavior.
Before relying on a skill-text edit, run the pressure method:

1. Write a scenario in which the edited rule should change what the agent does.
2. Run that scenario as a subagent without the new wording; this no-guidance
   baseline shows the uncontrolled behavior.
3. Run the same scenario with the edited text, at least five times per side.
4. Read the matches manually; a grep hit is not evidence of the behavior.
5. Keep a micro-test — a committed static pin or eval scenario — that
   distinguishes the guided behavior from the no-guidance control.

Two standing rules follow from the method: refining one skill always includes
its full pressure run for the edited rules, and a pressure run over the whole
skill corpus happens only on an explicit user request; it is never part of
future work by default.

### Standing evidence rules

- Run the no-guidance control in a clean environment without the repository
  checkout: a checkout leaks the edited wording into the baseline subagent
  through the `skills/` tree or project instructions.
- Put full absolute paths in subagent prompts. A relative path lets the
  subagent rationalize a wrong location (the `skills/skills/` antipattern)
  instead of failing on the missing file.
- Plan rate-limit capacity for at least two retries per side of a comparison;
  a run that cannot retry stops producing evidence exactly when it matters.
- Never accept a single "honest stop" as the verdict. In measured waves the
  protocol decided better than a one-shot stop (3-7% lost matches against
  8-15%); escalate through more iterations instead of trusting one refusal.
- Read npm and node:test results only from a written file. Piping the live
  output through another command shows false failures from the parallel
  reporter interleaving streams.

## Boundaries

- Portable skills are self-contained and do not depend on the repository or the
  OpenCode npm package after installation.
- Skills with external tools carry their environment contract inside the archive;
  the bundled runner only checks tools and prints repair commands, it never
  installs or removes anything.
- Cross-skill relations are install recommendations: the build materializes each
  skill's declared companions into its `SKILL.md` "Related skills" section, and
  every archive still works on its own.
- The supported distribution is `https://kisev.github.io/skills`; source
  provenance is recorded in its release metadata and linked from
  `https://github.com/kisev/skills/releases/latest`.
- The opt-in development distribution is `https://kisev.github.io/skills/dev`;
  only its current snapshot is retained.
- The stable portable installer is `npx --yes skills@latest`.
- Updates do not prune retired names automatically.
- Skills do not replace repository policy, review, secret scanning, or access
  control.
