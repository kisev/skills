# live-runs Specification

## Purpose

The synthetic live-run system (verification speed 2): one command turns a
versioned scenario into a real-model run in an isolated fixture, with a
pinned eval profile, engine adapters, and a verdict backed by transcript
evidence.

## Requirements

### Requirement: Pinned eval profile

Live runs MUST use a profile fixed in a versioned config file — engine,
engine profile, and budgets. The model is never pinned in the repository:
it is chosen entirely inside the host-side engine profile. The runner never
discovers or guesses a provider; a missing or unresolvable profile is a
loud instructive error, never a fallback to whatever happens to resolve.

#### Scenario: Running with the pinned profile

- **WHEN** a scenario is executed
- **THEN** the engine and engine profile come from the profile file and
  are named in the report, while the model stays a concern of the
  host-side engine profile

#### Scenario: Profile missing or broken

- **WHEN** the profile file is absent or its engine does not respond
- **THEN** the run stops with an instructive error pointing at the setup
  guide instead of substituting another provider

### Requirement: The engine is ccr behind a documented setup

The initial engine is ccr (claude-code-router), an external CLI dependency.
The repository MUST document how to install ccr and configure the dedicated
test profile on the host; credentials stay on the host and never enter the
repository.

#### Scenario: New contributor setup

- **WHEN** a contributor follows the ccr how-to guide
- **THEN** the profile preflight check passes and scenarios run

### Requirement: Engine adapters

The runner MUST talk to engines through a small adapter — start, parse,
and a preflight — over one subprocess pattern. Continue and cleanup slots
are added when a host actually requires them. Adding an engine means adding
an adapter; scenarios and the profile format do not change.

#### Scenario: New engine

- **WHEN** support for another agent CLI is added
- **THEN** only a new adapter is registered and existing scenarios run
  unchanged

### Requirement: Isolation contract

Each run MUST execute in an isolated empty workdir containing only the
fixture, with the engine's real HOME available for authentication and a
positive environment allowlist (allowlisted names only) so no credential can
ride along under any name. Nothing outside the fixture workdir is modified.

#### Scenario: Writes stay in the fixture

- **WHEN** a scenario session writes files
- **THEN** every change is inside the fixture workdir

#### Scenario: Credentials cannot ride along

- **WHEN** the engine subprocess environment is built
- **THEN** it contains only allowlisted names, so an arbitrarily named token
  is absent by construction

#### Scenario: Scoped permissions

- **WHEN** the engine subprocess is launched
- **THEN** file edits are auto-accepted inside the staged workdir and every
  wider tool grant is declared by the scenario, never granted blanket by
  the adapter

### Requirement: Scenarios are versioned artifacts

A scenario MUST be a directory in the repository: a fixture repository, a
prompt, and assertions. Creating a scenario adds a directory, not code.

#### Scenario: New scenario

- **WHEN** a skill's behavior change needs a live check
- **THEN** the author adds a scenario directory and runs it by name

### Requirement: One command end to end

A single task MUST execute a scenario end to end: load the profile, stage
the fixture, run the engine, evaluate assertions, and emit a report with a
verdict and transcript evidence.

#### Scenario: Fresh checkout

- **WHEN** a contributor with the ccr profile configured runs the task for
  a scenario by name
- **THEN** it finishes with a verdict and an evidence path, with no manual
  environment plumbing

### Requirement: Integration with the three-speed model

Live runs MUST be triggered per the verification model: one run on a
material behavior change, a full scenario sweep before a release, and
mechanically reproducible failures MUST sediment as speed-1 regressions.

#### Scenario: Material change

- **WHEN** a skill's behavior changes materially
- **THEN** its scenario runs once as part of the change

#### Scenario: Failure sediments

- **WHEN** a scenario failure is mechanically reproducible
- **THEN** a speed-1 regression check captures it before the change closes

### Requirement: Budgets and reporting

Every run MUST operate under explicit budgets (timeout, cost where
measurable) and produce a verdict plus redacted transcript evidence stored
outside Git.

#### Scenario: Timeout

- **WHEN** a run exceeds its timeout budget
- **THEN** it is reported as a timeout with partial evidence, not left
  hanging
