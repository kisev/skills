# Spec Delta

## Purpose

Defines how quality is checked in this project: three speeds of verification
with explicit triggers for each, replacing the previous maximalist
single-bar culture that conflicted with the 80/20 principle.

## ADDED Requirements

### Requirement: Speed 1 - fast programmatic checks on every change

Fast programmatic checks that require no model calls MUST run on every
change: skill structure validation (frontmatter, links, sizes, schemas),
unit and contract tests of runtime logic, the skill-text to runtime-surface
contract, and materialization reproducibility.

#### Scenario: Every change

- **WHEN** any change is made
- **THEN** speed 1 checks run automatically and complete quickly enough for
  pre-commit and CI use

### Requirement: Speed 2 - trigger-based synthetic live runs

Synthetic live runs (real model, synthetic scenario) SHALL be triggered only
by material changes to a skill's behavior or routing, not by prose edits.
A trigger run is one run per scenario, executed in isolated environments
without live service stands; the full catalog receives a sweep before a
release.

#### Scenario: Prose edit

- **WHEN** only skill prose changes
- **THEN** no synthetic live run is required

#### Scenario: Behavior change

- **WHEN** a skill's routing or behavior changes materially
- **THEN** one synthetic live run validates the change

#### Scenario: Release sweep

- **WHEN** a release is prepared
- **THEN** the whole catalog passes a synthetic live sweep

### Requirement: Speed 3 - organic usage without obligations

Acceptance on the owner's real tasks MUST NOT be a required gate. The owner
tries tools on real work at will; reported pain becomes a fix and, where
reproducible, a speed 1 or speed 2 regression.

#### Scenario: Pain report

- **WHEN** the owner reports a problem found in real usage
- **THEN** it is fixed and covered by a regression check where it can be
  reproduced

### Requirement: No fixed repeat counts for text edits

Repository rules MUST follow the three-speed triggers; no rule may require a
fixed number of repeated model runs for every wording change.

#### Scenario: Rules audit

- **WHEN** the repository's instruction and gate files are read
- **THEN** no rule demands repeated model runs for every wording change

### Requirement: Existing mechanisms justify themselves or shrink

Every existing verification mechanism (gates, preflights, publication
checks) MUST either justify its cost against the 80/20 principle or be
simplified or removed.

#### Scenario: Mechanism audit

- **WHEN** a verification mechanism cannot show that its cost yields
  proportionate value
- **THEN** it is simplified or removed
