# Design

## Context

The retired npm integration (`@kisev/agentomatic`, TypeScript, \~460 KB of
source) grew incrementally and encodes a hard-won safety model: preview,
confirmation digests, ownership manifests, drift protection, JSONC-safe
config conversion. The renegotiation decided not to port the code but the
contracts: the behavior is already specified in the legacy capability
specs (`specs/capabilities/package-tools/*` — reconcile, doctor,
config-setup, route, agent\_profiles), and the new implementation is
written small and fresh.

The delivery model is taken from openspec (studied from its 1.15.0
distribution): a single CLI carrying canonical skill sources, a host
registry (`{ host, skillsDir, legacySkillsDirs, detectionPaths }` style),
per-host materialization with dialect adaptation (verified in this very
checkout: `.agents` copies reference `/openspec-propose` while `.claude`
copies reference `/opsx:propose`), and update-time protection of files
the user edited after generation.

## Goals / Non-Goals

**Goals:**

- One tool, one command path, zero to working skills on Codex, Claude,
  and OpenCode — from the published distribution, without Node and
  without a checkout.
- The safety model of the retired integration, as contracts, not code.
- The owner can install unpublished working-tree content to themself.
- The npm line, agents, and routing disappear without traces in the
  repository.

**Non-Goals:**

- Multi-agent orchestration of any kind — the six agents and the routing
  layer die here; a future idea would enter as its own change.
- A general package manager — skillmate installs this project's content
  model only.
- Hosts beyond Codex, Claude, and OpenCode (the registry makes more
  possible; none are planned).

## Decisions

### D1. Name and home

The tool is `skillmate`: PyPI distribution, import package, and console
command. It lives at `apps/skillmate/` (user-run application; may declare
dependencies), Python 3.12+, uv tooling. The name `agentomatic` is taken
on PyPI by an unrelated active project; `skillmate` is free and reserved
under the owner's account `kisev`.

### D2. Adapter registry, openspec-style, with the verified table

One adapter per host as data: target directories per scope, command
surface format, dialect transforms, config writer. The canonical content
model (built skill archives plus their command surfaces) is shared and
never host-aware. Adding a host touches only the registry.

The adapter table, verified against host documentation (2026-10-25):

| Host | Skills, project | Skills, global | Commands, project | Commands, global | Config needed |
| - | - | - | - | - | - |
| Codex | `.agents/skills/` | `~/.agents/skills/` | none — custom prompts are deprecated and local-only (`~/.codex/prompts`), so the adapter reports the gap | none | none (`~/.codex/config.toml` `[[skills.config]]` only disables skills) |
| Claude | `.claude/skills/` | `~/.claude/skills/` | `.claude/commands/` | `~/.claude/commands/` | none |
| OpenCode | `.opencode/skills/` | `~/.config/opencode/skills/` | `.opencode/commands/` | `~/.config/opencode/commands/` | optional `opencode.json` skill permissions |

Sources: developers.openai.com/codex/skills and /codex/custom-prompts
(REPO `$CWD/.agents/skills` up to repo root, USER `$HOME/.agents/skills`,
symlinked skill folders followed; prompts deprecated),
code.claude.com/docs/en/skills (personal `~/.claude/skills/`, project
`.claude/skills/` up to repo root, symlinked skill entries load once,
`.claude/commands/*.md` as the command format),
opencode.ai/docs/skills and /docs/commands (project
`.opencode/skills/`, global `~/.config/opencode/skills/`, plus
Claude-compatible and agent-compatible fallback reads of `.claude/skills`
and `.agents/skills` in both scopes; `metadata["opencode/slash"]`
exposes a skill as a `/name` command).

Codex needs no command channel beyond skills: skills themselves are
invocable (`$skill-name`, `/skills`), which is the command surface there.

### D3. Dialect materialization

Each host's copy may differ from canonical content by deterministic
transforms declared in the adapter (slash-command naming and similar).
Transforms must be reversible to canonical, so drift detection and
updates compare against the canonical form. This mirrors the observed
openspec behavior and is the reason per-host copies are copies, not
symlinks.

### D4. Sources: distribution first, checkout as dev mode

The primary source is the versioned Pages distribution manifest — the
same artifact `npx skills` consumes, which keeps minimum compatibility
with that channel for free. `--from-checkout <path>` is the dev-only
source for unpublished or experimental content; it stamps the
installation as dev. There is no fallback between sources: an
unreachable, unpinned, or malformed source is a loud error.

### D5. Safety model ported as contracts

Preview of the full plan, explicit confirmation, ownership manifests
(paths plus digests plus version), collision detection against foreign
files, and drift preservation. The legacy capability specs are the
behavioral reference; golden tests are written from them first, then the
implementation. The retired TypeScript code is read for edge cases, not
copied.

### D6. Host configuration, minimal and format-faithful

skillmate touches host configuration only where installed content needs
it. OpenCode keeps the proven fragment model (plugins, permissions; only
needed sections; comments and foreign entries preserved; conflicts
reported). Codex and Claude start from whatever their hosts actually
require for skill discovery — possibly nothing — verified against host
documentation, never assumed.

### D7. Oblivion for the retired surfaces

Everything in-repo goes: the package tree, the workspace publication
graph, agents, routing, the npm release automation, the
`opencode-integration` how-to pair, CLI reference entries, catalog
mentions, mise pins. The `npm-package-lifecycle` how-to and project skill
are rescoped to the PyPI lifecycle or removed. Honest limit: artifacts
already published to the npm registry and GitHub release history cannot
be fully erased; registry cleanup is best-effort under npm policy, and
published history is history, not a reference.

### D7. Scope boundary for the legacy specs tree

The `specs/` capability tree still describes the retired package
surfaces (agents, routing, package tools). Its retirement is renegotiate-foundation's
task 3.2, so this change removes the functional surfaces and every
current-facing mention, and leaves `specs/` untouched; the 6.2
verification "no artifact remains anywhere" is read over the functional
repository (packages, assets, gates, docs, automation), not over that
legacy tree.

### D8. Delivery and verification

PyPI release through trusted publishing (GitHub OIDC) from `main`, a
python sibling of the release discipline without the npm graph. Speed-1
verification: contract tests per adapter and per safety behavior against
fixtures, wired into the repo gates. The installer is deterministic —
no speed-2 scenario is required for it; post-install skill behavior
stays covered by the existing live-runs scenarios.

## Risks / Trade-offs

- \[OpenCode reads `.claude/skills` and `.agents/skills` too, so an
  install for all three hosts makes OpenCode see the same skill name in
  three locations, and its docs ask for unique names across locations] →
  task 3.4 verifies OpenCode's actual duplicate behavior and the adapter
  resolves it (dedup by name is expected to prefer the native
  `.opencode` directory; if not, the dialect transform or permissions
  settle it) before install-for-all ships.
- \[The safety port is where regressions hide] → golden tests from the
  legacy specs are written before the implementation (D5).
- \[Two channels during migration: npm line stays until 6.x completes] →
  the removal tasks are inside this change, so the overlap is bounded by
  the change's lifetime, not by policy.
- \[A single-word generic name on PyPI can be squatted elsewhere] → only
  PyPI matters for delivery; the name is registered by the owner now.
