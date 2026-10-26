# Spec Delta

## Purpose

The canonical generalization layer of the project: mission, target users,
non-negotiable principles, and the capability map that every other spec
builds on. This is the single place that answers what the project is, who it
serves, and what it stands for, without requiring a tour of per-capability
specs.

## ADDED Requirements

### Requirement: The project maintains a charter

The repository SHALL maintain a charter that states the mission, the target
users, and the non-negotiable working principles of the project.

#### Scenario: Reading the foundation

- **WHEN** a reader opens the charter
- **THEN** they learn what the project is, who it serves, and which
  principles govern every capability, without opening any other spec

### Requirement: The charter states the mission and audience

The charter SHALL record that this is a personal-first project that grows
from the owner's real needs, is public from the start for users with the
same needs, and consciously trades simplicity for universality.

#### Scenario: Newcomer asks what this project is

- **WHEN** someone asks what the project is and who it is for
- **THEN** the charter answers in one place, including the deliberate
  simplicity-versus-universality trade-off

### Requirement: The charter tracks the capability map

The charter SHALL stay current with the project's capability map: every
published capability is reflected in it, and every component verdict (core,
rework, deferred, deleted) is recorded there.

#### Scenario: Capability archived

- **WHEN** a change that adds or removes a capability is archived
- **THEN** the charter's capability map reflects it afterwards

#### Scenario: Asking what is core

- **WHEN** someone asks which components form the current core set
- **THEN** the charter lists them with their status

### Requirement: The project stays a monorepo

The project SHALL remain a single repository; splitting into separate
repositories is a deliberate future decision, not an assumed one, and is
taken only when the shape has stabilized.

#### Scenario: Cross-cutting change

- **WHEN** a change touches skills, applications, and infrastructure
  together
- **THEN** it is executed inside the one repository without
  package-boundary ceremony
