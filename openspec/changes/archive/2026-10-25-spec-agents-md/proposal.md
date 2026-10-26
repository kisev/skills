# Proposal

## Why

`agents-md` is a core skill confirmed in the foundation renegotiation (see
`renegotiate-foundation`): frequently used and staying. This change gives
the component its exhaustive specification and executes the renegotiation
decision that concerns it: CLAUDE.md support, which the skill knows nothing
about today.

## What Changes

The skill stays a text-only reconcile-and-validate workflow over AGENTS.md
files: find every applicable file from the worktree root to the target
scope, collect facts from the checkout, keep the shared section intact, cap
project rules, remove stale and inherited duplicates, write atomically, and
validate.

New behavior — the CLAUDE.md mirror, decided in the renegotiation and
confirmed by the owner in this change's clarification round:

- AGENTS.md is the canonical file; beside every AGENTS.md the skill manages
  (root and nested), a CLAUDE.md mirror is maintained.
- The mirror is a symlink to the sibling AGENTS.md when the environment
  supports symlinks, otherwise a full copy.
- A CLAUDE.md that exists and differs from the sibling AGENTS.md is never
  modified silently: the skill asks how to synchronize and recommends
  synchronizing (consolidating unique content into AGENTS.md and restoring
  the mirror form).

## Capabilities

### New Capabilities

- `agents-md`: repository agent-instruction maintenance — the
  reconcile-and-validate workflow over AGENTS.md files, its fact and hygiene
  rules, and the CLAUDE.md mirror for hosts that read a different
  instruction file.

### Modified Capabilities

None.

## Impact

`skills/agents-md` (SKILL.source.md, references/workflow\.md,
references/agents-md-guidelines.md), the skill catalog entries (EN/RU), and
every repository where the skill runs: a CLAUDE.md file or symlink appears
beside each managed AGENTS.md on the next reconcile run.
