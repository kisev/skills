# Tasks

## 1. Skill text

- [x] 1.1 Extend references/workflow\.md with the mirror algorithm: create
  beside every managed AGENTS.md (root and nested), symlink-first with
  full-copy fallback, mirror validation (symlink resolves to the sibling or
  content equals it), and the diverged-file ask-and-recommend path;
  integrate the mirror into the post-write validation step — verification:
  structure lint green; the workflow names the mirror in the algorithm and
  the Result section
- [x] 1.2 Add the mirror policy to references/agents-md-guidelines.md
  (canonical file, mirror forms, divergence handling) — verification: the
  guidelines contain the policy and stay self-contained
- [x] 1.3 Update the SKILL.source.md description to mention the CLAUDE.md
  mirror — verification: description lint green; discovery terms intact

## 2. Verification

- [x] 2.1 Run the speed-1 structure checks over the edited skill —
  verification: checks pass
- [x] 2.2 Run one synthetic live run (speed 2) on a fixture repository
  covering the three mirror paths: fresh mirror creation at root and a
  nested scope, symlink-failure copy fallback, and a diverged CLAUDE.md
  asking instead of overwriting — verification: the run transcript shows
  all three behaviors; reproducible failures sediment as speed-1
  regressions

## 3. Documentation

- [x] 3.1 Update the skill catalog entries (EN/RU) with the mirror
  behavior — verification: locale parity check passes

## Workflow follow-up

- Archiving this change creates the `agents-md` capability spec under
  openspec/specs/.
- No relation changes: the skill stays without dependencies.
