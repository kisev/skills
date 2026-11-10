# Spec Delta

## MODIFIED Requirements

### Requirement: Engine adapters

The runner MUST talk to engines through a small adapter — start, parse, and a
preflight — over one subprocess pattern. Continue and cleanup slots are added
when a host actually requires them. Adding an engine means adding an adapter
and its host-side profile name; scenarios do not change, and every profile
keeps the same keys.

#### Scenario: New engine

- **WHEN** support for another agent CLI is added
- **THEN** only a new adapter is registered and existing scenarios run unchanged

#### Scenario: Host-side profile name

- **WHEN** a profile declares its host-side engine profile
- **THEN** the adapter receives that name and the report records it, without a repository-pinned model

## ADDED Requirements

### Requirement: Selectable engine profiles

The runner MUST accept an explicit profile file with the same schema as the
default `evals/live/profile.json`; the default remains the ccr profile, and a
missing or invalid profile MUST stop with an instructive error.

#### Scenario: Selecting a host profile

- **WHEN** a caller passes a profile file for another host
- **THEN** the run uses that profile's engine, host-side profile name, and budgets

#### Scenario: Missing selected profile

- **WHEN** the selected profile file is absent or malformed
- **THEN** the run stops with the exact path and repair guidance instead of falling back to the default

### Requirement: Cross-host scenario runs

The runner MUST be able to execute the same versioned scenario through the ccr,
opencode, and codex adapters, MUST name the host and engine profile in the
report, and MUST block with the missing CLI instead of substituting another
host.

#### Scenario: Same scenario on another host

- **WHEN** the same scenario is run with an opencode or codex profile
- **THEN** the scenario, fixture, prompt, and assertions are unchanged and the report names the host

#### Scenario: Missing host CLI

- **WHEN** the selected host CLI is not installed
- **THEN** preflight reports the exact missing executable and the run does not start

#### Scenario: Cross-host evidence

- **WHEN** a cross-host run finishes
- **THEN** the report records the host, engine profile, verdict, and redacted transcript outside Git
