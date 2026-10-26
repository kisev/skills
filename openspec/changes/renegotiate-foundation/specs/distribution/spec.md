# Spec Delta

## Purpose

How the project's artifacts reach users: one installer-configurator for
skills, commands, and host configuration across all supported hosts, with a
host-adapter architecture and a preserved safety model.

## ADDED Requirements

### Requirement: Single entry point for installation and configuration

`agentomatic` SHALL be the single tool that installs skills, lays out
commands, and configures host settings for Codex, Claude, and OpenCode, in
both project and global scopes.

#### Scenario: One-command setup

- **WHEN** a user runs the installer for the selected hosts
- **THEN** skills, commands, and host configuration are set up without
  calling scattered unrelated tools

### Requirement: Host-adapter registry

Host-specific wiring SHALL live in a host-adapter registry: one canonical
content model, and per-host adapters that know only the target path and the
file format for that host.

#### Scenario: New host adapter

- **WHEN** support for a new host is added
- **THEN** the content model is unchanged and only a new adapter is
  registered

### Requirement: Safety model is preserved

The installer MUST keep its safety model: a preview of planned changes,
explicit confirmation before writes, ownership manifests that detect
collisions, and preservation of user drift on update.

#### Scenario: User-modified file

- **WHEN** an installer-owned file was modified by the user
- **THEN** an update does not overwrite it silently

#### Scenario: Preview before write

- **WHEN** the installer plans changes
- **THEN** it shows them and waits for confirmation before writing

### Requirement: No external installer dependency

Installation of this project's skills MUST NOT require the external `skills`
CLI; it stops being the primary install channel.

#### Scenario: Install without the external CLI

- **WHEN** the project's skills are installed
- **THEN** the external `skills` CLI is not invoked
