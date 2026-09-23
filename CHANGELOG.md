# Changelog

All notable changes to this project are documented in this file. Entries follow
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); release numbers follow
[Semantic Versioning](https://semver.org/).

[Русская версия](CHANGELOG.ru.md)

## Unreleased

### Changed

- `task-triage` now supports incremental single-issue and collection-wide GitLab
  triage with private XDG artifacts, shared task-review assessment, SemVer,
  priorities, dependencies, and manual update commands.

## \[6.0.0] - 2026-09-22

### Added

- `spec-manage` now supports one project-selected canonical language, natural
  mode selection, indexed specification extensions, specialized requirement and
  architecture profiles, deterministic audits, and a portable Python 3.12+
  structural validator with explicit snapshot and lifecycle checks.
- `release-prepare` now builds one stable pre-merge and post-merge publication
  runbook bound to the exact release inventory, milestone, contributors,
  reviewers, work-item decisions, immutable payloads, and manual `glab`
  commands.
- `stopit` now provides a standard-library runner for private, atomic,
  workspace-scoped handoffs under the XDG state directory.

### Changed

- `task-prepare` publication drafts now use stable `plan_key` slots with
  content-addressed immutable support files, atomic replacement, and slot-scoped
  locking.
- Behavioral evaluations can assert structured per-case outcomes and observed
  mutation boundaries. Hostless evaluation now uses materialized skills and no
  longer presents fixture expectations as observed model behavior.

### Fixed

- Portable skill artifact paths remain stable across reruns while changed
  payloads are retained immutably and unsafe or stale writes fail closed.

### Breaking Changes

- `task-prepare` publication input is now version 2 and requires a safe
  lowercase `plan_key`; regenerate version 1 bundles and update references from
  content-derived directories to `.task-prepare/<plan_key>/`.
- `stopit` replaces unique temporary handoff files with
  `$XDG_STATE_HOME/agent-skills/stopit/<workspace-id>/handoff.md`; update tools
  that retain old temporary paths.
- Release publication plans and `artifact-contracts-v2` release records have new
  required bindings and decisions. Regenerate existing release plans instead of
  reusing older artifacts.
- Existing canonical specification trees must declare `Canonical language:` in
  `specs/README.md` and satisfy the new formal structure before validation can
  pass. Resolve mixed-language trees explicitly before updating them.

## \[5.1.3] - 2026-09-21

### Fixed

- EditorConfig checks now invoke the installed `editorconfig-checker` binary
  instead of the unconfigured local alias `ec`. The `v5.1.2` clean-runner
  preflight stopped before artifacts were created because that alias was absent.
- Releases now require a clean pre-tag `release/vX.Y.Z` branch workflow before
  `main` and the annotated tag are pushed. Local validation no longer requires
  an unpublished tag or incorrectly assumes the release commit is already on
  `origin/main`.

## \[5.1.2] - 2026-09-21

### Fixed

- Mise now uses its npm installer for npm-backed tools, ensuring `npm_args`
  installs the pinned Remark plugins on clean runners. The `v5.1.1` preflight
  stopped before artifacts were created because the default Aube installer
  ignored those plugin arguments.

## \[5.1.1] - 2026-09-21

### Fixed

- GitHub Actions are pinned to immutable commit SHAs again, satisfying the
  repository's enforced action policy. The `v5.1.0` workflow was rejected before
  any jobs or artifacts were created; `v5.1.1` is the corresponding release
  correction.

## \[5.1.0] - 2026-09-21

### Added

- Code review now assesses the MR contribution separately from the accumulated
  next-release SemVer impact, using verified release catalogs and target-branch
  evidence with an explicit fallback when no release basis can be established.
- Code review now inspects the complete job inventory for the MR-bound exact-head
  pipeline, including bounded failed-job traces and recursively collected
  downstream pipelines.

### Changed

- CI now materializes portable skills once and fans the immutable artifact out
  to direct Task targets instead of routing checks through `ci:*` aggregators.
- The package metadata now pins skills installer `1.7.0`, and compatibility
  verification covers the configured OpenCode `1.18.31` toolchain.
- Repository quality gates now use the pinned Mise toolchain, strict Python type
  and lint checks, focused pre-commit hooks, and one documented `task pre-push`
  gate. Existing portable skill and OpenCode package consumers require no
  migration.

### Fixed

- Code review now binds pipeline evidence to the merge request, falls back to the
  verified MR target snapshot when the current target commit is unavailable
  locally, and redacts authorization headers, cloud credentials, credentialed
  URLs, JSON secrets, and private keys from failed-job traces.

### Removed

- Removed machine specification traceability, commit-impact trailers, hooks, and
  CI enforcement. Canonical Markdown specs and semantic `spec-manage` workflows
  remain the source of truth.

## \[5.0.0] - 2026-09-18

### Added

- MR preparation now produces stable bilingual publication plans, project
  templates, manual `glab` commands, and evidence-bound freshness checks.

### Fixed

- Clarified when askme applies and how manual continuation proceeds. npm release
  verification now tolerates registry propagation delays.

### Breaking Changes

- MR preparation requires locale-bound drafts with exhaustive label assessments.
  Regenerate legacy drafts and publication plans.

## \[4.1.1] - 2026-09-17

### Fixed

- Code-review reports show the release version stamped at build time, compact MR
  metadata, one label delta with its command, and readable reply/state actions.
  Internal action fields and duplicate patch previews no longer clutter reports.
- Closed threads with a verified explanation or applied suggestion no longer
  require redundant replies. Workflow guidance uses humanize and prefers
  semantically equivalent namespaced labels over plain labels.
- Local fixes retain copy-ready patch previews. Regression coverage includes
  report layout, semantic label replacement, and reproducible version stamping.

## \[4.1.0] - 2026-09-17

### Added

- Code review now audits every open and resolved discussion on every invocation,
  including unchanged MRs. Its contract-5 plans bind decisions to the complete
  discussion chronology, keep `unchanged` explicit, and validate optional fixing
  commit attribution without exposing a SHA.

### Changed

- Code review now requires a validated suggestion or patch for accepted thread
  findings, enforces matching resolve/reopen state transitions, prepares comment
  and thread-state commands separately, and renders unanchored fixes as
  copy-ready `git apply` heredocs.

## \[4.0.0] - 2026-09-17

### Changed

- Bounded project-file workflows now write directly with atomic replacement;
  preview/confirmation protocols remain only for external publication, user
  configuration, destructive cleanup, history changes, releases, and package
  lifecycle operations.
- Code review now prepares direct manual `glab` commands and body files. GitLab
  discussions, notes, and issues authored by the current user are the source of
  truth for incremental publication assessment.

### Removed

- The digest-confirmed `review_publish.py` helper, publication receipts, hidden
  publication markers, retry state, and postcondition verification are removed.
- Confirmation-based project-write flows, including `ast-grep rewrite --apply`
  and the former work-item/team artifact apply phases, are removed.

## \[3.2.1] - 2026-09-16

### Fixed

- Code review rejects structurally duplicate accepted findings before producing or
  applying a publication plan, so an independent critic cannot create a second
  comment for the same issue.
- The GitLab publication helper sends JSON requests with an explicit
  `Content-Type`, allowing confirmed line discussions to be accepted by GitLab.

## \[3.2.0] - 2026-09-16

### Added

- Code review now has a resumable runner-owned state machine with `status`,
  `next`, generated critic/decision/content templates, and final chat rendered
  only from a fresh contract-4 publication plan.

### Changed

- `skills-opencode reconcile` no longer inspects or removes portable skills or
  their lock files. Deleted upstream skills are handled by `skills update/remove`.
- Portable lifecycle documentation now directs installation, updates, listing,
  and removal through the official skills CLI.

### Security

- Code review fails closed on incomplete, out-of-order, or stale evidence,
  critic, decision, plan, Markdown, and baseline bindings. Review activation and
  confirmed publication share one lock, preventing superseded plans from being
  reported or executed.

## \[3.1.1] - 2026-09-16

### Release

- Republishes the 3.1.0 code-review fix artifacts and diagnostics under a new
  immutable tag because npm recorded 3.1.0 without a downloadable tarball.
- Runtime, schemas, documentation, and compatibility behavior are unchanged from
  3.1.0; release verification now tolerates bounded registry propagation delay.

## \[3.1.0] - 2026-09-16

### Added

- Code review prepares one validated fix artifact for every actionable finding,
  thread correction, and author-local fix: an exact GitLab suggestion when the
  diff position supports it, or a content-addressed unified patch otherwise.
- Publication plans show fix mode, operation, position, patch digest, full diff,
  and manual `git apply --check` and `git apply` commands.

### Changed

- The publication helper reports bounded redacted request diagnostics and
  distinguishes definitive GitLab rejection from uncertain mutation outcomes.
- Structured contract-2 plans remain executable, while older baselines fall back
  to a full review before producing contract-3 fix artifacts.

## \[3.0.0] - 2026-09-16

### Added

- Code review can prepare digest-bound GitLab comments, discussion replies, issue
  proposals, and label changes. Every action is confirmed separately, revalidates
  live state, and records a resumable local receipt.
- `skills-opencode reconcile` archives exact-owned retired assets before cleanup,
  preserves user-owned or modified files, and rolls planned paths back when a
  confirmed operation fails.

### Changed

- OpenCode administration is CLI-only. `skills-opencode capabilities`, `doctor`,
  `reconcile`, `agent`, and `critic` keep their deterministic interfaces, while
  the core plugin exposes only the receipt-bound `route` tool.
- The supported public inventory is 27 portable skills, 27 same-named skill
  commands, 6 agents, 3 optional plugins, and 1 package tool.

### Removed

- The generic `doit` skill and command are removed; normal engineering work now
  follows the active host and repository instructions directly.
- The portable `lsp-report` skill and command are removed; use
  `skills-opencode doctor` for OpenCode LSP reporting.
- The `/agent-profiles`, `/capabilities`, `/doctor`, and `/reconcile` command
  adapters and their package tools are removed.

### Migration

- Update the package, then run `skills-opencode reconcile --dry-run` and its exact
  confirmation command to archive and remove unchanged retired package assets.
- Remove installed `doit` and `lsp-report` copies with `skills remove`, or let a
  confirmed package reconciliation remove copies carrying the Pages source marker.

## \[2.4.2] - 2026-09-16

### Release

- Republishes the 2.4.1 documentation and locale-validation fixes under a new
  immutable release tag because npm recorded 2.4.1 without a downloadable tarball.
- Documentation, locale contracts, and runtime behavior are unchanged from 2.4.1.

## \[2.4.1] - 2026-09-16

### Fixed

- Public documentation now provides structurally aligned English and Russian
  versions with natural localized prose and separate changelog and security files.
- Locale validation now detects mismatched Markdown blocks, and portable cleanup
  guidance includes the `summary` to `briefing` rename.

## \[2.4.0] - 2026-09-16

### Added

- Code review once again supports incremental workflows with persisted evidence,
  reviewer plans, and structured output for follow-up rounds.
- Specification management preserves decision history and provides explicit
  traceability for its lifecycle requirements.

### Changed

- The `summary` skill and command are renamed to `briefing`; catalog,
  migration inventory, documentation, and evaluation triggers use the new name.
- Local release gates now use the single `task pre-push` entrypoint before a
  branch and its annotated release tag are pushed atomically.

## \[2.3.1] - 2026-09-15

### Fixed

- OpenCode installer upgrades that deselect every fixed agent now preserve the
  separate profile configuration while removing managed profiles without rollback.

## \[2.3.0] - 2026-09-15

### Added

- Structured root and contextual CLI help now documents every command and group,
  accepted options, safe mutation workflow, scope behavior, and examples.
- Unified terminal selectors add consistent keyboard guidance and true
  multi-selection for arbitrary command, agent, and plugin subsets during install.
- Diataxis documentation adds focused tutorials, how-to guides, reference
  material, and explanations for portable skills and the OpenCode integration.

### Changed

- User documentation now points to stable npm channels, while generated OpenCode
  confirmation commands retain exact package versions and global CLI execution is
  independent of the current directory.
- Project release, portable installer, and OpenCode compatibility versions now
  come from centralized, validated sources of truth; per-skill metadata versions
  were removed in favor of distribution metadata and content-addressed archive digests.

## \[2.2.3] - 2026-09-15

### Fixed

- Code review output now includes plain absolute artifact paths, explicit MR
  metadata and SemVer assessments, and one immutable manual publication command
  per finding even for merged or closed merge requests.
- Review publication commands revalidate MR state, exact head SHA, and body
  digest before posting while remaining preview-only and never executing GitLab
  mutations automatically.

## \[2.2.2] - 2026-09-14

### Fixed

- npm post-publication verification now retries the attestations endpoint while
  registry provenance propagates, without accepting a mismatched artifact.
- GitHub artifact uploads use the supported Node 24 action runtime.

## \[2.2.1] - 2026-09-14

### Added

- Root agent guidance, pull request ownership and review templates, exhaustive
  JSON Schema validation with concrete instances, and locked dependency audits.
- Exact cross-channel release manifests, npm registry smoke checks, signature and
  SLSA provenance verification, and automated GitHub Release creation.

### Changed

- CI now runs independent specification, static, Python, portable-distribution,
  evaluation, package, and secret-scanning gates with one stable aggregate check.
- One tag workflow performs the complete preflight before publishing the exact
  Pages and npm artifacts and verifies both channels after publication.
- Strict Python typing and formatting now cover maintained skill-local runners
  and all previously excluded maintained source files.

### Fixed

- Canonical pytest discovery now includes the 41 Mattermost-local regression
  tests, and pre-commit checks handle deletions, schemas, specs, and toolchain files.
- Ordinary push CI no longer runs on release tags, removing the historical tag
  specification-range failure mode.

## \[2.2.0] - 2026-09-14

### Added

- Release-tag CI now deploys the portable distribution to GitHub Pages and
  verifies the served release metadata, archive paths, and SHA-256 digests.
- The Pages payload exposes the agentskills.io discovery `0.2.0` index and one
  deterministic content-addressed archive per public skill.

### Changed

- Portable installation now uses the continuously updated stable source
  `https://kisev.github.io/skills` instead of Git repository selectors.
- Authored entrypoints are named `SKILL.source.md`; shared contracts and runtimes
  are injected only into ignored `.build/skills` output, removing 126 committed
  generated copies from the source tree.
- `@kisev/skills-opencode@2.2.0`, portable distribution metadata, release tag,
  and GitHub Release are version-aligned to the same commit while retaining
  independent installation and update lifecycles.

### Migration

- Existing Git-based portable installations remain bound to their old source.
  Repeat `skills add` with `https://kisev.github.io/skills` and the same scope and
  agents to rebind them before using `skills update`.

## \[2.1.0] - 2026-09-14

### Added

- Team workflows now support strict private profiles, automatic default-profile
  resolution, guided self-setup from explicit files, URLs, repositories, or
  connector evidence, and digest-bound profile updates outside the public repository.
- `team-retro` and `team-roadmap` include complete evidence workflows and a
  bounded GitLab period collector with strict `[since, until)` semantics,
  pagination, deduplication, timestamp provenance, and explicit partial results.
- `slides-prompts-prepare` combines a user-selected theme with concise factual
  team, project, technology, and delivery references while preserving one prompt
  per slide and existing images.
- Mattermost reading now includes origin- and user-isolated SQLite caching,
  exact-scope access revalidation, reaction and membership collection, bounded
  periods, and confirmed cache cleanup.
- GitLab preparation workflows can derive semantic label recommendations from
  the live label catalog without replacing unrelated labels.
- Code review and release preparation include role-aware evidence, architecture
  checks, release inventory, and companion artifact guidance.

### Changed

- `agents-md`, `commit-msg`, and `humanize` use stronger evidence boundaries and
  more explicit output contracts.
- Team profile files require private filesystem permissions and never place raw
  profile content in preview plans or reports.
- Portable metadata for Mattermost and the five shared team workflows is now
  `2.1.0`; the OpenCode package, release tag, and documentation use the same version.

### Fixed

- Mattermost eval fixtures now track the current GET-only and stdin-cookie
  contracts.
- Pre-commit checks isolate their Git environment, and GitLab eval/schema
  formatting remains deterministic.

## \[2.0.6] - 2026-09-11

### Fixed

- Trusted Goal Mode authorization now covers every action explicitly listed in
  the frozen accepted objective without a redundant confirmation prompt.
- Synthetic continuations, untrusted markers, and later prompts cannot approve
  pending actions or expand the accepted objective.
- Offline policy runners now enforce bounded paths, shared timeouts, stable JSON
  errors, and compatibility with the previous GitLab evidence scenario.

## \[2.0.5] - 2026-09-11

### Fixed

- Legacy preview receipts are accepted and replaced during the next preview.
- Legacy `2.0.3` preview receipts are normalized and replaced by the next
  preview instead of failing with `invalid_receipt`.

## \[2.0.4] - 2026-09-11

### Release

- Republishes the 2.0.3 installer, reconcile, and receipt lifecycle fixes under
  a new immutable release tag because `v2.0.3` already exists.
- Portable skill metadata remains `2.0.0`; inventory and archive ownership are
  unchanged.

## \[2.0.3] - 2026-09-11

### Fixed

- The installer wizard now explicitly distinguishes skill command adapters from
  package command adapters and explains that portable skills are installed separately.
- The human-readable reconcile preview is blocked by modified managed assets or ownership
  conflicts, lists every blocking path, and shows remediation instead of Apply.
- A new dry run in one scope supersedes an older unconsumed preview across installer,
  reconcile, agent, and critic operations; plan and confirmation digests are separate,
  and a superseded confirmation is rejected.
- A blocked reconcile creates no new receipt and does not disclose confirmation details.
- Documentation now records persistent npm installation, installer confirmation,
  plugin activation, and restart before reconcile.

### Unchanged

- Portable skill metadata remains `2.0.0`; inventory, runtime, agents, plugins, and
  manifest schema are unchanged.

## \[2.0.2] - 2026-09-10

### Fixed

- The CI specification-impact helper now handles an annotated tag push correctly:
  it compares the tag object from `event.after` with the commit from `GITHUB_SHA`, then
  builds the range from the first parent of the release commit.
- A regression test covers the `v2.0.0` failure with a zero-before value and failed run
  `https://github.com/kisev/skills/actions/runs/34496801895`.

### Unchanged

- Runtime, skills, public inventory, and behavioral contracts are unchanged.

## \[2.0.1] - 2026-09-10

### Fixed

- The CI specification-impact gate now resolves ranges deterministically for pull
  requests, regular branch pushes, first branch pushes, and tag pushes.
- A tag push no longer passes a zero SHA to Git: the gate verifies that the release
  commit is reachable from `origin/main`, then builds the impact range from its
  first parent.
- Invalid, missing, and unreachable event SHAs cause the gate to fail closed.

### Unchanged

- This is a CI-only fix: runtime, skills, public inventory, and behavioral contracts
  are unchanged. Portable skill metadata remains `2.0.0`.

## \[2.0.0] - 2026-09-10

### Breaking changes

- Skills `attempt`, `schedule`, `usage`, and `overview` are removed without a
  replacement.
- `project-spec`, `skill-improver`, and `walkthrough` are renamed to `spec-manage`,
  `skill-improve`, and `code-explain`, respectively.
- `team-workflow` is replaced by five fixed skills: `team-sprint-start`,
  `team-sprint-close`, `team-retro`, `team-roadmap`, and `slides-prompts-prepare`.
- Legacy skill, command, and plugin surfaces are removed, including the `/route` slash
  command; the `route` package tool remains available without a slash command.
- Action and mode aliases are removed: the public surface uses only exact names from
  the catalog.

### Installation and migration

- Portable skills install directly from the GitHub tag with a pinned executable
  (replace `opencode` with `codex` for Codex):

  ```shell
  npx --yes skills@1.5.23 add https://github.com/kisev/skills/tree/v2.0.0 \
    --agent opencode --skill '*' --copy --yes
  ```

- An exact migration from `v1.2.0` uses the migration inventory and preserves
  ownership and hash evidence; renamed skills require manual verification of the
  new name.

- Reconcile moves retired exact-owned assets into a private content-addressed archive
  with `archive-pending` status; modified, user-owned, and unknown assets remain
  conflicts. Archive, restore, and purge are not included in this release.

### OpenCode

- `@kisev/skills-opencode@2.0.0` is compatible with OpenCode `>=1.18.29 <1.19.0`
  and requires Node.js 22+.
- Portable skills and the optional OpenCode integration are installed independently;
  the integration does not include skills or modify `opencode.json`.

### Known limitations

- Mattermost does not yet have full parity with the stated scenarios.
- Runtime state and `doctor` require further hardening.
- Stateful plugins remain opt-in; the scheduler and related wrappers are disabled by
  default; `ast-grep` and `rtk` require preinstalled CLIs.
- Live evaluation is not part of the ordinary quality gate and runs only explicitly in
  a trusted environment.

## \[1.2.0] - 2026-09-07

### Added

- A unified versioned `work-item/v1` contract for `askme`, `task-prepare`,
  `task-review`, and `goal`, with a canonical schema, materialized validator, and
  deterministic structured reports.
- An optional independent premortem for complex work items with explicit decisions
  by the primary agent.

### Changed

- `goal` became a read-only portable `work-item/v1` generator; lifecycle and
  auto-continuation are removed. Historical state remains for future classification.

## \[1.1.1] - 2026-09-06

### Changed

- The installer CLI now shows a concise human-readable plan and agent inventory table
  by default; complete stable JSON is available only with `--json`.
- Preview prints a ready-to-run confirm command and collapses long path groups without
  hiding conflicts, digest, TTL, or the restart flag.

## \[1.1.0] - 2026-09-06

### Added

- A direct CLI for inventory, configuring models and variants of fixed agents, explicit
  reconcile, and safely adding or removing additional critics.
- The `agent_profiles` package tool and four optional thin slash commands without a
  dedicated skill.
- Separate profile configuration and a semantic deployment manifest with an exact
  critic pool, rendered hashes, and preserved settings during a package update.

### Changed

- The complete manager, critic, and review contracts now require a fresh card and
  approval, prohibit direct worker remediation, and use exact allowlists without
  prefix wildcards.
- Ownership of fixed agents moves from the generic installer into the profile domain;
  commands and plugins remain under generic ownership.
- All installer and profile mutations use private receipts with a TTL, lifecycle lock,
  final inventory validation, and a journaled all-or-rollback transaction with recovery.

### Security

- An exact-name user-owned collision blocks apply, unknown agents are not changed, and
  a `1.0.0` migration requires an exact manifest and SHA-256 match.
- State primitives prohibit symlink targets and parents, use private modes and atomic
  writes, and append safely.

## \[1.0.0] - 2026-09-05

### Added

- The first public stable release of portable Agent Skills.
- The independent `@kisev/skills-opencode` npm package with an opt-in OpenCode
  installer, agents, commands, and plugin factories.
- Documentation for installing skills, enabling OpenCode, updating, uninstalling, and
  security boundaries.

### Security

- Write-capable skills and the installer use preview with explicit confirmation.
- The OpenCode installer retains an ownership manifest and does not overwrite other
  or user-modified files.
- After the v1.0.0 bootstrap, the npm package is published from GitHub Actions through
  OIDC trusted publishing without a long-lived publish token.
