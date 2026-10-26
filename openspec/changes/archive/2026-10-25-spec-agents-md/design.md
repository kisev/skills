# Design

## Context

The skill is text-only today: a thin SKILL.source.md, a 15-step workflow,
and a guidelines reference carrying the standard shared section and
checklists. It has no scripts and no relations. The renegotiation confirmed
it as core and added one decided rework: CLAUDE.md support via symlink —
the skill currently knows nothing about CLAUDE.md. Host facts that shape
the mirror: Codex and OpenCode read AGENTS.md natively; Claude Code reads
CLAUDE.md and follows symlinks.

## Goals / Non-Goals

**Goals:**

- One source of truth for agent instructions per scope, readable by all
  three supported hosts.
- The mirror integrated into the existing reconcile-and-validate workflow
  as first-class behavior (create, validate, audit), not a bolt-on step.

**Non-Goals:**

- Other host instruction files (.cursorrules, .clinerules, and similar) —
  the three supported hosts only.
- Automatic merging of diverged CLAUDE.md content — divergence always goes
  through the user.
- Scripts or runtime tools — the skill stays text-only.

## Decisions

### D1. AGENTS.md is canonical; CLAUDE.md is its mirror

A CLAUDE.md symlink pointing to the sibling AGENTS.md, beside every managed
file. Alternatives rejected: CLAUDE.md canonical (inverts the open standard
the skill manages); generated copies everywhere (drift); no mirror (Claude
Code reads nothing).

### D2. Mirror beside every managed AGENTS.md, including nested

Claude Code reads CLAUDE.md at the root and in the subdirectories it works
in; a root-only mirror would leave nested scopes unread. The root-only
alternative was rejected by the owner.

### D3. Symlink by default, full copy on unsupported environments

Detection is by attempt: create the symlink; if creation fails, write a
full copy. Validation accepts either form — a symlink resolving to the
sibling AGENTS.md, or a regular file equal to it in content.

### D4. Diverged CLAUDE.md: ask, recommend, never overwrite silently

When a CLAUDE.md exists and differs (a real file or a drifted copy), the
skill does not touch it: it shows the divergence and asks how to
synchronize, recommending synchronization — consolidate unique CLAUDE.md
content into AGENTS.md, then restore the mirror form. This follows the
project's drift-protection culture and the mutual-understanding principle.

### D5. The mirror lives in skill text, not scripts

The skill has no runtime; mirror actions are agent-executed and verified by
one synthetic live run (speed 2) covering the three paths: fresh mirror,
copy fallback, diverged file.

## Risks / Trade-offs

- \[Checkouts without symlink support materialize a symlink as a plain file
  containing the target path] → such a file differs from AGENTS.md and
  enters the divergence path: the skill reports it and offers the copy
  form; nothing is overwritten silently.
- \[The mirror adds a file to repositories that may not want it] → the
  mirror is the skill's decided contract; an existing or diverged CLAUDE.md
  always goes through the user, so the cost is one question, not damage.
- \[Copy mirrors drift over time] → audit and validation compare content and
  route drift into the divergence path.

## Migration Plan

Skill-text change only; no data or repository migration. Repositories
touched by the skill after this change gain the mirror on their next
reconcile run; existing diverged CLAUDE.md files are handled by D4.

## Open Questions

None — direction, scope, fallback, and divergence policy were decided by
the owner in this change's clarification round.
