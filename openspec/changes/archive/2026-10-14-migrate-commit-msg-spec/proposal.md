# Proposal

## Why

The legacy canonical specification (`specs/`) has drifted from the shipped skill
behavior: `specs/capabilities/skills/commit-msg.md` still mandates an English
commit message, while `skills/commit-msg/references/workflow.md` has derived the
message language from repository instructions, commit configuration, and history
since commit `b6ef7f1`. The repository is migrating to OpenSpec, where spec
deltas travel inside the same change as behavior changes. `commit-msg` is the
pilot capability for that migration.

## What Changes

- Create the OpenSpec capability `commit-msg`: the single canonical contract for
  commit message generation. Eight requirements with scenarios cover the current
  skill behavior — environment check, evidence base, scope resolution, atomicity
  guard, convention detection, one-line output contract, default format, and the
  read-only guarantee — plus the `/commit-msg` command adapter binding (the
  essence of legacy `REQ-I-206`).
- Retire the legacy capability records
  `specs/capabilities/skills/commit-msg.md` and
  `specs/capabilities/commands/commit-msg.md` in the same change, so the
  capability keeps exactly one canonical text and no dangling cross-references
  remain in the legacy tree.
- Update the `specs/capabilities/README.md` inventory row and adapt
  `scripts/check_documentation.py` so a migrated surface no longer requires a
  legacy capability record; the check learns a migrated-surfaces list instead.
- No runtime, skill-text, or built-artifact changes: the skill and command
  behave exactly as before; only the canonical contract moves.

Out of scope: migrating any other capability, the shared requirements and
crosscutting-concept layers of `specs/`, and deciding the migration order
between per-capability files and the shared layer (recorded in
[design.md](design.md) as an open program-level question).

## Capabilities

### New Capabilities

- `commit-msg`: generate one concise commit message from local changes —
  scope resolution, atomicity and convention guards, the one-line output
  contract, the default message format, read-only execution, and the
  `/commit-msg` command binding to this capability.

### Modified Capabilities

None. This is the first OpenSpec spec in the project; no existing OpenSpec
capabilities are modified.

## Impact

- `openspec/specs/commit-msg/spec.md` — new (lands via this change's delta at
  archive time).
- `specs/capabilities/skills/commit-msg.md`,
  `specs/capabilities/commands/commit-msg.md` — deleted.
- `specs/capabilities/README.md` — inventory row updated for the migrated
  surfaces.
- `scripts/check_documentation.py` — migrated-surface handling added.
- No changes under `skills/`, `shared/`, `packages/`, or `.build/`; no
  behavioral change to the skill or the command adapter.
