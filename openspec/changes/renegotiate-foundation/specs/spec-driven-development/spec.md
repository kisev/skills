# Spec Delta

## Purpose

OpenSpec is the only specification system used by this project and practiced
by its tools; a companion layer adds the generalization that per-capability
specs alone do not provide.

## ADDED Requirements

### Requirement: OpenSpec is the only spec system

This project SHALL use OpenSpec as its single specification system; no
parallel in-house spec tree is maintained.

#### Scenario: Single home

- **WHEN** a behavior of any component is specified
- **THEN** its spec lives under `openspec/` as a capability spec

### Requirement: The legacy specs tree is migrated, not extended

The legacy `specs/` tree is legacy: still-valuable content SHALL be migrated
into OpenSpec (charter, capability specs, decisions), and nothing new is
added to the legacy tree.

#### Scenario: New requirement

- **WHEN** a new requirement is agreed
- **THEN** it is captured in OpenSpec, never in the legacy tree

### Requirement: Spec skills are OpenSpec companions

The spec-skill family (reworked from `spec-manage`) SHALL work as OpenSpec
companions: maintaining the generalization layer — charter, capability map,
cross-cutting decisions — and onboarding projects into OpenSpec, complementing
rather than duplicating OpenSpec's own workflows.

#### Scenario: Overview without a tour of specs

- **WHEN** a user asks what a project is built on
- **THEN** the companion layer answers from the generalization layer without
  requiring a walk through every capability spec

#### Scenario: Coexistence with OpenSpec workflows

- **WHEN** a task is covered by an OpenSpec workflow (propose, apply,
  archive)
- **THEN** the companion skills defer to it instead of reimplementing it

### Requirement: Documentation skills route to OpenSpec

Skill texts that route specification work (currently `docs-prepare` and
`docs-review`) SHALL route spec-level drift to OpenSpec and the companion
layer instead of the legacy tree.

#### Scenario: Spec drift found in a docs review

- **WHEN** a documentation review finds a spec-level discrepancy
- **THEN** it is reported against OpenSpec content
