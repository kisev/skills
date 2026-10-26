# Tasks

## 1. Decisions and scaffold

- [x] 1.1 Record the clarification decisions in the proposal — name
  skillmate, sources distribution+checkout, per-host placement with
  dialects, PyPI delivery, full removal of the npm line, agents, and
  routing — verification: this artifact set carries them
- [x] 1.2 Scaffold `apps/skillmate/`: pyproject (distribution `skillmate`,
  console script, Python 3.12+), uv tooling, and a CLI skeleton whose
  five commands parse arguments and print empty previews — verification:
  `uv run --project apps/skillmate skillmate --help` and each subcommand
  `--help` work locally without network
- [x] 1.3 Verify each host's global directories and command mechanisms
  against current host documentation and freeze the adapter table in
  design — verification: every table row cites its source; unverifiable
  rows are dropped rather than assumed

## 2. Content model and sources

- [x] 2.1 Canonical content model (built skill archives plus command
  surfaces) and the distribution manifest client: fetch, version
  resolution, integrity check — verification: unit tests against a
  fixture manifest and a local file source; offline behavior tested
  without network
- [x] 2.2 The dev checkout source behind an explicit flag, stamping
  installations as dev — verification: an install from the repository
  working tree installs unpublished content and reports the dev stamp

## 3. Host adapters

- [x] 3.1 Adapter registry core: placement per scope, command formats,
  dialect transforms, and config writers as data — verification:
  registry unit tests, including transform reversibility to canonical
- [x] 3.2 Codex adapter (`.agents` project scope; verified global
  location; prompts where supported) — verification: adapter contract
  tests
- [x] 3.3 Claude adapter (`.claude` project scope; verified global
  location; command format) — verification: adapter contract tests
- [x] 3.4 OpenCode adapter (`.opencode` project scope; verified global
  location; commands and config fragments ported from the legacy
  contracts) — verification: adapter contract tests plus golden tests
  from the legacy config-setup specification

## 4. Safety model

- [x] 4.1 Preview of the complete plan and explicit confirmation before
  any write — verification: unit tests prove no write path bypasses
  preview and confirmation
- [x] 4.2 Ownership manifests and foreign-file collision detection —
  verification: collision fixtures (existing foreign file, missing
  manifest, stale manifest) each produce the specified report
- [x] 4.3 Drift preservation: user-modified owned files are reported and
  never silently overwritten on update or remove — verification: drift
  fixtures for update and remove

## 5. Lifecycle commands

- [x] 5.1 `install` — hosts and scope selection, per-host
  materialization with dialects, ownership recording — verification:
  end-to-end install test against a fixture project and distribution
- [x] 5.2 `update` — version selection, per-file delta preview, drift
  handling — verification: update tests across versions of a fixture
  distribution
- [x] 5.3 `remove` — per host and scope, owned files only, drifted-file
  confirmation — verification: remove tests over an installed fixture
- [x] 5.4 `doctor` — missing files, version drift, foreign collisions,
  stale ownership records — verification: broken-install fixtures each
  produce the named diagnosis and repair
- [x] 5.5 `status` — installed versions per host and scope,
  machine-readable — verification: status output parses and matches the
  installed fixture

## 6. Removal of the retired surfaces

- [x] 6.1 Delete `packages/agentomatic/` and its complete workspace and
  npm publication graph (bindings, release automation, lockfile entries)
  — verification: workspace installs and builds clean without the
  package; no orphaned references in task or gate composition
- [x] 6.2 Delete the six agents and the routing layer together with the
  package — verification: no agent or routing artifact remains anywhere
  in the repository
- [x] 6.3 Clean every mention: `opencode-integration` how-to pair, CLI
  reference, skill catalog, READMEs, mise pins, and the site —
  verification: repository search for the retired names returns no
  functional reference; registry cleanup is best-effort under npm policy
  and recorded as such
- [x] 6.4 Rescope or remove the `npm-package-lifecycle` how-to and
  project skill in favor of a PyPI lifecycle document — verification:
  lifecycle documentation describes exactly one publication channel

## 7. Documentation

- [x] 7.1 Install how-to EN/RU (uvx and pip paths, hosts and scopes, the
  dev checkout mode) added to the locale manifest; CLI reference gains
  the skillmate command set — verification: locale and documentation
  checks pass

## 8. Delivery and verification

- [x] 8.1 PyPI delivery: packaging metadata, trusted-publishing workflow
  from `main`, first-release checklist under the owner's account —
  verification: a dry-run publish passes and the workflow refuses
  untagged or non-main runs
- [x] 8.2 Speed-1 wiring: adapter and safety contract tests run in the
  repository gates with inputs registered in `gate-registry.json` —
  verification: `task gates:check` and the scoped pre-push gate stay
  green
