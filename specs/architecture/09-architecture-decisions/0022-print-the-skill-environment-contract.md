# ADR-0022: Print the skill environment contract instead of shipping an installer

- Status: accepted
- Date: 2026-10-15
- Status changed: none
- Supersedes: none
- Superseded by: none

## Context and problem statement

Skills installed through the external `skills` CLI stopped being sufficient in
practice: the archives carry only text, while the sessions need external tools
(`git`, `glab`, `uv`/`uvx`, npm packages from this repository). Those tools arrive
through three uncoordinated channels — the skills Pages channel, ephemeral `uvx`
installs from Git pins, and npm packages — with no consistency check, and the
runtime pin was stitched by a hard-coded special case for one skill
(`code-review`). Users hit silent breakage, most visibly the wrapper-plugin
failure after every dev re-pin.

## Decision drivers

- Keep the external `skills` CLI as the only skill-text channel; do not add a
  fourth installation channel (decision 4 admits external CLI engines, not new
  meta-installers).
- Make every environment requirement discoverable and repairable from the
  installed artifact itself, in the spirit of the printed-contract doctrine.
- Derive every pin from one channel revision so skill texts, the Git runtime
  pin, and the workspace npm pin can be cross-checked locally without network.

## Considered options

- A meta-installer wrapping `skills`, npm, and `uv`. Rejected: duplicates the
  external skills CLI and adds a maintained surface.
- Make the agentomatic installer own skill installation. Rejected: it is
  OpenCode-specific and would take over a foreign domain it currently does not
  touch.
- Print the contract from the artifact. Accepted: each archive with external
  dependencies carries a materialized requirements manifest, a stdlib-only
  check runner, and skill texts that require the first session to run the check
  and show the output.

## Outcome

`shared/runtime-requirements.json` is the authored inventory (11 archives with
external dependencies). The distribution build stitches
`references/requirements.json` into every listed archive from the single
channel revision and prints a local channel verdict (manifest pin, index
revision, workspace npm pin; never the registry). Each archive ships
`scripts/check_environment.py`, a standard-library-only runner that prints one
OK/FAIL line per tool with a copy-ready repair command, supports `--json`,
installs nothing, and makes no network call. `agentomatic doctor` reads the
same installed manifests for OpenCode users. The legacy
`references/runtime-pin.json` is absorbed: new archives stop emitting it and
skill texts fall back to it only when `requirements.json` is absent.

## Consequences

- Skill archives stay text-self-sufficient while the environment contract
  makes their runtime needs explicit, checkable, and repairable with printed
  commands.
- The build-time hard-coded pin for `code-review` is gone; every dependency
  archive gets the same mechanism and the parity is pinned by contract tests.
- The npm re-pin defect itself (AGENT-7) stays a separate fix; this contract
  detects it and prints the repair, but does not mutate the npm project.

## Compatibility

Installed archives without `requirements.json` keep working through the
documented legacy `runtime-pin.json` fallback and the existing checkout-path
pin resolution. `agentomatic doctor` reports an honest "not found" verdict on
machines without manifests.

## Migration

`skills update` installs archives that carry the manifest and the runner; the
code-review skill text reads `source_revision` from `requirements.json` first
and from the legacy pin only as a fallback.

## Rollback

Remove the requirements entries from the distribution build and restore the
`runtime-pin.json` special case; the runner and manifest are additive archive
payloads.

## Reversibility

Fully reversible: the contract is additive metadata plus an optional runner;
no stored artifact schema changed.

## Risks

- The inventory can drift behind a new skill that grows an external
  dependency; the inventory test fails closed by enumerating archives with
  external dependencies.
- `rtk` has no public installer, so its repair line is honest guidance rather
  than a copy-ready command.

## Links

- [REQ-F-566](../../requirements/functional/README.md) — skill environment
  contract
- [REQ-I-428](../../requirements/interfaces/README.md) — reviewmatic runtime
  pin source
- [ADR-0021](0021-run-reviewmatic-from-python-git-sources.md) — Git-sourced
  runtime that the pin selects
