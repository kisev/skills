# AGENTS.md guidelines

Read this reference when updating `AGENTS.md` requires the standard shared
section or a fact-gathering checklist.

## Standard shared section

Copy this section unchanged when the shared section is absent or must be restored.

```markdown
## General rules

### Language and style

- Reason and respond in the language of the latest user request; use English when it is ambiguous.
- Write code comments and commit messages in English.
- Write documentation and user-facing text in the language established by the repository; use English if no standard is explicit.
- Preserve the style, structure, and abstraction level used by analogous files in this repository.
- Be concise and critical: identify risks, disputed decisions, and strong alternatives.
- If user intent is unclear and an error could affect a release, compatibility, or security, ask one short clarifying question.

### Core engineering rules

- Deliver complete implementations without stubs.
- Before making changes, examine the minimum sufficient set of relevant files,
  including analogous implementations, tests, and documentation; expand the set
  for monorepos or multiple build systems.
- Start with this repository's rules and structure, then use its documentation.
- Do not invent branch, merge/pull-request, or deployment rules; take them from
  current repository configuration or canonical documentation.
- Do not duplicate existing utilities, templates, or logic blocks.
- Base change verification only on available facts.
- If data is insufficient, explicitly label the conclusion as an assumption.
- Do not make a finding without a clear risk, impact, or minimal remediation.
- Consider edge cases, security, input validation, compatibility, and performance.
- Remove unused code and do not complicate the solution unnecessarily.
- Add comments only when the code's purpose or constraint is not obvious.
- After changes, explicitly state completed and unrun checks.

### Document maintenance rules

- Keep the shared section as consistent as possible across repositories; put differences in the project section.
- Do not replace project rules with the shared template or remove user-specific clarifications without reason.
- Keep `AGENTS.md` compact.
- Add only rules that are genuinely applicable and verifiable in this repository.
```

## Context checklist

Check the project manifest, task configuration, CI, formatters and linters, source
and test layout, documentation, and the actual lint, test, build, typecheck, and
format commands. Do not invent commands: confirm them from configuration.

## Project-rule constraints

- At most 20 bullets, with one bullet per line.
- Do not add subsections inside project rules.
- Include key paths, actual commands, CI, environment variables, dependencies,
  and runtime/toolchain version constraints.
- Do not copy large documentation excerpts: retain the agent's required action
  and, where useful, a short link to the canonical file.
