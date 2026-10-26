# agents-md Specification

## Purpose

Maintains repository agent instructions (AGENTS.md) from repository facts
across scopes, and keeps a CLAUDE.md mirror beside every managed file so
all three supported hosts read one source of truth.

## Requirements

### Requirement: One reconcile-and-validate workflow

The skill SHALL treat create, update, reduce, and audit as composable parts
of one reconcile-and-validate workflow over AGENTS.md files, not as
mutually exclusive modes.

#### Scenario: Missing file

- **WHEN** no applicable AGENTS.md exists for the target scope
- **THEN** the workflow creates it

#### Scenario: Audit without changes

- **WHEN** reconciliation produces no diff
- **THEN** the skill reports the file as current and writes nothing

### Requirement: Scope and inheritance

The skill SHALL find every applicable AGENTS.md from the worktree root to
the target scope, including nested files whenever the parent scope changes,
and MUST NOT duplicate parent instructions in a nested file; conflicts with
parent and nested files are checked before writing.

#### Scenario: Nested scope

- **WHEN** the target scope is a subdirectory with its own concerns
- **THEN** a nested AGENTS.md contains only scope-specific rules

### Requirement: Checkout as the source of truth

The local checkout, including uncommitted changes, SHALL be the source of
truth. When only a remote repository is available, the skill MUST read
files at the exact requested revision through hosting tools without
producing remote effects.

#### Scenario: Uncommitted changes

- **WHEN** candidate rules depend on files with uncommitted changes
- **THEN** the collected facts reflect the working tree, not the last
  commit

### Requirement: Fact-based rules only

Every rule MUST be verifiable from repository facts (commands, paths,
versions, CI behavior, environment variables, ownership constraints);
branch, merge/pull-request, and deployment rules are included only when
repository configuration or canonical documentation confirms them. A
private rule-to-source map is maintained and is not printed unless
requested.

#### Scenario: Unverifiable rule

- **WHEN** a candidate rule cannot be traced to a source
- **THEN** it is not added and the unconfirmed constraint is reported

### Requirement: Shared section integrity

The standard shared section SHALL be restored unchanged from the reference
when missing or damaged; its meaning changes only on an explicit user
request.

#### Scenario: Damaged shared section

- **WHEN** the shared section deviates from the reference
- **THEN** it is restored verbatim

### Requirement: Project rule cap

Project rules SHALL be at most 20 one-line bullets without subsections,
retaining only rules that prevent frequent errors or specify non-obvious
commands or boundaries.

#### Scenario: Over the cap

- **WHEN** reconciliation yields more than 20 candidate rules
- **THEN** only the highest-value rules are kept and the dropped ones are
  reported

### Requirement: Hygiene

Stale, unconfirmed, and exact inherited duplicate rules SHALL be removed;
user refinements MUST NOT be replaced with the template unless they
conflict with repository facts.

#### Scenario: User refinement

- **WHEN** a user-specific clarification does not conflict with facts
- **THEN** it is preserved

### Requirement: Language preservation

The skill SHALL preserve the language established by existing repository
instructions and MUST NOT translate confirmed instructions solely to match
the response language.

#### Scenario: English instructions, Russian request

- **WHEN** the repository's instructions are in English and the
  conversation is in Russian
- **THEN** the files remain in English

### Requirement: Atomic write, diff, and post-validation

The bounded project file SHALL be written with atomic replacement, the
resulting diff shown, and content, nesting, and scope validated after
writing.

#### Scenario: Write and validate

- **WHEN** the file is written
- **THEN** the diff is shown and validation confirms only applicable rules
  with no stale or inherited duplicates

### Requirement: CLAUDE.md mirror beside every managed file

Beside every AGENTS.md the skill manages, a CLAUDE.md mirror SHALL be
maintained: a symlink to the sibling AGENTS.md when the environment
supports symlinks, otherwise a full copy of it.

#### Scenario: Fresh mirror

- **WHEN** an AGENTS.md is created or updated and no CLAUDE.md exists
  beside it
- **THEN** a symlink to that AGENTS.md is created

#### Scenario: No symlink support

- **WHEN** symlink creation fails in the environment
- **THEN** a full copy of the AGENTS.md is written as the mirror

#### Scenario: Mirror validation

- **WHEN** the workflow validates a scope
- **THEN** the mirror is valid if it is a symlink resolving to the sibling
  AGENTS.md or a regular file whose content equals it

### Requirement: Diverged mirror asks, never overwrites silently

When a CLAUDE.md exists and differs from the sibling AGENTS.md, the skill
MUST NOT modify it silently; it SHALL ask the user how to synchronize and
recommend synchronizing: consolidating the unique content into AGENTS.md
and restoring the mirror form.

#### Scenario: Real diverged CLAUDE.md

- **WHEN** a non-mirror CLAUDE.md with different content exists
- **THEN** the skill presents the divergence, proposes consolidation, and
  writes only after the user's choice

#### Scenario: Drifted copy

- **WHEN** a copy-mirror no longer equals its AGENTS.md
- **THEN** the same ask-and-recommend path applies

### Requirement: Agent instructions only

The skill SHALL manage agent instruction files only; README.md,
CONTRIBUTING.md, and similar documentation are out of scope.

#### Scenario: Documentation request

- **WHEN** asked to rewrite README.md
- **THEN** the skill declines and points to documentation tooling
