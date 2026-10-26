# skillmate Specification

## Purpose

skillmate is the single installer-configurator for the project's portable
skills, their command surfaces, and host configuration across Codex,
Claude, and OpenCode, in project and global scopes, with the safety model
of preview, confirmation, ownership, and drift preservation.

## Requirements

### Requirement: Single entry point

skillmate SHALL install portable skills, lay out their command surfaces,
and configure host settings for Codex, Claude, and OpenCode in one tool,
in both project and global scopes. No other repository tool owns any part
of this lifecycle.

#### Scenario: One-command setup

- **WHEN** a user runs skillmate install for the selected hosts
- **THEN** skills, commands, and needed host configuration are set up
  without calling any other repository tool

### Requirement: Host-adapter registry

Host-specific wiring SHALL live in a host-adapter registry: one canonical
content model, and one adapter per host that knows only the target
directories per scope, the command surface format, the dialect
transforms, and the configuration format of that host.

#### Scenario: New host adapter

- **WHEN** support for another host is added
- **THEN** the content model is unchanged and only a new adapter is
  registered

### Requirement: Content placement per host and scope

The adapter table SHALL place skills and commands into the host-native
directories: Codex under `.agents`, Claude under `.claude`, and OpenCode
under `.opencode`, in the project scope; and under the host's global
location in the global scope. Every global path MUST be verified against
the host's current documentation before the adapter table is frozen.

#### Scenario: Project-scope install

- **WHEN** skills are installed for all three hosts in a project
- **THEN** each host's directory contains the host's materialized copy

#### Scenario: Global-scope install

- **WHEN** skills are installed with the global scope
- **THEN** they land in the global location of each selected host

### Requirement: Per-host dialect materialization

Each host's copy MAY differ from the canonical content by dialect
transforms declared in that host's adapter, such as slash-command naming
conventions. The canonical content model MUST stay single and unchanged;
transforms MUST be deterministic and reversible to the canonical form.

#### Scenario: Dialect difference

- **WHEN** a skill references a command whose invocation syntax differs
  between hosts
- **THEN** each host's copy carries that host's syntax and no other
  difference

### Requirement: Content sources

skillmate SHALL install from the versioned remote distribution (the Pages
manifest) as its primary, always-available channel, preserving minimum
compatibility with `npx skills` as a consumer of the same distribution.
A local checkout SHALL be supported as a dev-only source, selected by an
explicit flag, for unpublished or experimental versions; a checkout MUST
never be required for normal use.

#### Scenario: Install from the distribution

- **WHEN** a user installs without source flags
- **THEN** content comes from the pinned versioned distribution manifest

#### Scenario: Dev install from a checkout

- **WHEN** the owner installs with the checkout flag pointing at a local
  repository
- **THEN** the unpublished working-tree content is installed and reported
  as a dev installation

#### Scenario: Distribution unreachable

- **WHEN** the distribution manifest cannot be fetched
- **THEN** the command fails with an instructive error and never falls
  back to a guessed source

### Requirement: Versioning and update

Every installation SHALL record the content version it installed. Update
SHALL move an installation to a selected version through the same
preview-and-confirmation path as install.

#### Scenario: Update to a newer version

- **WHEN** the distribution publishes a newer version
- **THEN** update previews the per-file delta and applies it after
  confirmation

#### Scenario: Pinned version

- **WHEN** a version is pinned explicitly
- **THEN** install and update use exactly that version

### Requirement: Safety model

skillmate MUST keep the retired integration's safety model: a preview of
all planned changes before any write, explicit confirmation before
writes, ownership manifests that detect collisions with files skillmate
does not own, and preservation of user drift — a file the user modified
after installation is never silently overwritten.

#### Scenario: Preview and confirm

- **WHEN** any command would write
- **THEN** it first prints the complete plan and writes only after
  explicit confirmation

#### Scenario: Foreign file collision

- **WHEN** a target path exists and is not owned by skillmate
- **THEN** the collision is reported and the file is left untouched

#### Scenario: User drift

- **WHEN** an owned file was modified by the user after installation
- **THEN** update reports the drift and does not overwrite it

### Requirement: Removal

Removal SHALL uninstall only files skillmate owns, per host and scope,
through the same preview-and-confirmation path. Drifted owned files MUST
be reported and removed only with explicit confirmation.

#### Scenario: Uninstall

- **WHEN** a user removes an installation
- **THEN** only owned files disappear and everything else stays

### Requirement: Command surfaces per host

A skill's command surfaces SHALL be materialized in each host's native
command format and directory: OpenCode commands, Claude commands, and
Codex prompts where the host supports them; where a host has no command
mechanism, the adapter reports the gap instead of inventing a format.

#### Scenario: Command installed per host

- **WHEN** a skill with a command surface is installed for all hosts
- **THEN** each host receives the command in its native format

#### Scenario: Host without a command mechanism

- **WHEN** a host has no native command mechanism for a surface
- **THEN** the adapter reports the unsupported surface and continues

### Requirement: Host configuration setup

skillmate SHALL apply host configuration changes only where a host needs
them for installed content to work, converting only the needed sections
of the host's configuration file, preserving existing entries and
comments, and reporting conflicts instead of merging them blindly.

#### Scenario: Needed fragment

- **WHEN** installed content requires host configuration
- **THEN** only the needed sections are converted, with existing entries
  and comments preserved

#### Scenario: Conflicting configuration

- **WHEN** an existing configuration entry conflicts with a needed one
- **THEN** the conflict is reported and nothing is merged silently

### Requirement: Doctor

skillmate SHALL provide a doctor command that diagnoses installations
per host and scope: missing files, version drift against the
distribution, foreign collisions, and stale ownership records, with both
human and machine-readable output.

#### Scenario: Broken installation detected

- **WHEN** an installation is missing files or drifted from its recorded
  version
- **THEN** doctor names each problem, its scope, and the exact repair

### Requirement: CLI contract

The command set (install, update, remove, doctor, status) SHALL follow
the repository's CLI conventions: configuration precedence, environment
variables, machine output, and diagnostics as defined by the shared CLI
reference.

#### Scenario: Machine output

- **WHEN** a command runs with the machine flag
- **THEN** it emits a stable, parseable result document and nothing else
  on stdout

### Requirement: Delivery on PyPI

skillmate SHALL be delivered as the PyPI distribution `skillmate`,
installable with `pip install skillmate` and runnable without
installation through `uvx skillmate`. The console command and the import
package are both `skillmate`; the implementation is Python 3.12+.

#### Scenario: uvx run

- **WHEN** a user runs `uvx skillmate install` without prior installation
- **THEN** the tool runs from the published distribution

### Requirement: Retired surfaces are gone

The npm package line, the six fixed agents, and the capability routing
layer SHALL be removed completely: no packages, no publication bindings,
no documentation entries, and no references remain in the repository
after this change.

#### Scenario: No traces

- **WHEN** the repository is searched for the retired surfaces after
  this change
- **THEN** no functional reference or mention remains
