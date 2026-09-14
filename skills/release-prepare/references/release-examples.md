# Release description examples

All projects, changes, people, tasks, and links below are fictional. Use these examples only as structure and detail guidance when the project has no release template. A project-specific format always has priority.

## Minor release with several MRs

```markdown
### Summary

Release v2.3.0 adds dependency caching and fix-branch support and adjusts the default build timeout.

### Compatibility and migration

- **Compatibility:** existing behavior remains supported
- **Migration:** projects with an explicit `BUILD_TIMEOUT` keep their configured value; other projects receive the new default
- **Deprecation timeline:** none

### Added

- **Dependency caching.** Change: a shared job caches dependencies between repeated builds. Impact: repeated pipelines finish faster. Team action: none. !101, [PLAT-101](https://tracker.example/issue/PLAT-101)

- **Fix-branch support.** Change: fix branches use the same verified path as feature branches. Impact: fixes can be validated before merge without separate configuration. Team action: none. !102, [PLAT-102](https://tracker.example/issue/PLAT-102)

### Changed

- **Build timeout.** Change: the default `BUILD_TIMEOUT` increases from 20 to 30 minutes. Impact: large projects time out less often. Team action: check project overrides. !103

### Links

- MRs: !101, !102, !103
- Issues: [PLAT-101](https://tracker.example/issue/PLAT-101), [PLAT-102](https://tracker.example/issue/PLAT-102)

---

**Contributors:** @developer.one, @developer.two

**Reviewers:** @reviewer.one

Thank you to everyone who contributed to this release.
```

## Patch release with a regression fix

```markdown
### Summary

Release v2.3.1 fixes environment cleanup after a canceled deployment.

### Compatibility and migration

- **Compatibility:** the change is backward compatible
- **Migration:** none
- **Deprecation timeline:** none

### Fixed

- **Environment cleanup.** Previous behavior: after a canceled deployment, the cleanup job did not receive the environment name and exited before deleting temporary resources. Change: the environment name is passed to every cleanup path. Impact: temporary resources are removed after canceled deployments. Team action: none. !104, [PLAT-103](https://tracker.example/issue/PLAT-103)

### Links

- MRs: !104
- Issues: [PLAT-103](https://tracker.example/issue/PLAT-103)

---

**Contributors:** @developer.three

**Reviewers:** @reviewer.one, @reviewer.two

Thank you to everyone who contributed to this release.
```

Describe a regression's cause and effect without personal judgment or unnecessary attribution. Link the introducing MR only when it helps explain compatibility or history.

## Release with a direct commit

A direct commit belongs in the changelog alongside MRs and retains its verified author.

```markdown
### Summary

Release v2.4.0 adds cache-policy selection and fixes a configuration example.

### Compatibility and migration

- **Compatibility:** existing behavior remains supported
- **Migration:** none
- **Deprecation timeline:** none

### Added

- **Cache-policy selection.** Change: `CACHE_POLICY` accepts `pull`, `push`, and `pull-push`. Impact: projects can select a mode without copying the job. Team action: none. !105

### Fixed

- **Configuration example.** Previous behavior: the example used an obsolete variable. Change: the example now matches the current schema. Impact: users can copy it without manual correction. [`0123456`](https://gitlab.example/platform/ci/example-templates/-/commit/0123456789abcdef0123456789abcdef01234567)

### Links

- MRs: !105
- Direct commits: [`0123456`](https://gitlab.example/platform/ci/example-templates/-/commit/0123456789abcdef0123456789abcdef01234567)

---

**Contributors:** @developer.one, Example Contributor

**Reviewers:** @reviewer.two

Thank you to everyone who contributed to this release.
```

For a direct commit, resolve a GitLab username only from an exact verified email match. Otherwise use the Git author name without guessing.

## Key rules

- Begin every item with a bold summary followed by a period.
- State the verified change, impact, team action, and source.
- For a fix, state the previous behavior, correction, and user-visible effect.
- Remove empty changelog sections.
- Always include compatibility and migration, even when no action is required.
- Link a direct commit by its seven-character SHA and full commit URL.
- Collect contributors from component MRs and direct commits. Deduplicate by username, then normalized email or name.
- Include reviewers only when approvals were actually collected. Exclude an MR author only from reviewers of that same MR.

## Short announcement

```markdown
## example-templates v2.4.0 released

### Highlights

- Cache policy can now be selected without copying CI jobs
- The configuration example now uses the current variable name
- Existing projects continue to work without migration

### Who should act

- Teams with custom cache jobs: check whether the shared template can replace them
- Other teams: no required action

---

[Documentation](https://docs.example.com/example-templates) |
[Releases](https://gitlab.example/platform/ci/example-templates/-/releases) |
[Issues](https://gitlab.example/platform/ci/example-templates/-/issues)
```

An announcement is a short explanation of release outcomes, not a copy of the full changelog. Keep 3-5 important points and only necessary actions.

## Illustration prompt

```markdown
# Illustration prompt

Horizontal editorial illustration, 16:9, about flexible and reliable CI caching: several independent build streams converge into a shared cache layer and then separate into completed artifacts. Calm technical composition, clean geometric forms, deep dark background, blue and warm orange accents, a sense of order and acceleration. No text, letters, numbers, code, logos, interfaces, screenshots, or recognizable brands.
```

Represent one or two verified release outcomes through a clear visual metaphor. Do not depict the whole changelog or add claims absent from the inventory.
