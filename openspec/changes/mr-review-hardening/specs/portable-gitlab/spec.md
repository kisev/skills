# Spec Delta

## Purpose

The shared v2 GitLab artifact contract validates evidence, publication, and
release artifacts for the active GitLab workflows. This capability owns which
profiles, scopes, artifact kinds, and publication actions that contract accepts.

## ADDED Requirements

### Requirement: Only active workflow profiles are accepted

The shared v2 GitLab artifact contract SHALL accept only the profiles used by
active workflows and SHALL reject the retired `code-review` profile and the
`local` target scope.

#### Scenario: Active prepare profile

- **WHEN** an artifact declares the `mr-prepare` profile with a merge request target
- **THEN** the contract accepts it

#### Scenario: Retired review profile

- **WHEN** an artifact declares the `code-review` profile
- **THEN** the contract rejects it as an unknown profile

#### Scenario: Retired local scope

- **WHEN** a target declares the `local` scope
- **THEN** the contract rejects it as an unsupported scope

### Requirement: Retired review artifacts are not part of the contract

The shared v2 GitLab artifact contract SHALL NOT define or accept
`local_wip_snapshot`, `local_review_report`, `review_context`, `review_plan`,
`review_decision`, or `critic_receipt` artifacts.

#### Scenario: Local WIP snapshot

- **WHEN** an artifact declares the `local_wip_snapshot` kind
- **THEN** schema validation rejects the unknown kind

#### Scenario: Retired review plan

- **WHEN** an artifact declares the `review_plan` or `review_decision` kind
- **THEN** schema validation rejects the unknown kind

#### Scenario: Active artifact still validates

- **WHEN** a `publication_plan`, `evidence_snapshot`, `context_package`, or release artifact for an active profile is supplied
- **THEN** schema and contract validation accept it

### Requirement: Retired local-fix and review publication actions are rejected

The shared v2 GitLab artifact contract SHALL NOT accept `local_fix` thread
outcomes or draft-note types, and SHALL NOT accept the
`code-review/publication-action/v1` publication action schema.

#### Scenario: Local fix outcome

- **WHEN** a review artifact carries the `local_fix` thread outcome or draft type
- **THEN** the contract rejects it

#### Scenario: Retired publication action

- **WHEN** a publication plan embeds a `code-review/publication-action/v1` action
- **THEN** the contract rejects the action schema

### Requirement: Removed artifacts have no compatibility mode

The shared v2 GitLab artifact contract SHALL NOT provide a compatibility mode,
alias, or migration for the retired review and local-WIP artifacts; a supplied
retired artifact SHALL fail validation instead of being accepted silently.

#### Scenario: Retired artifact is supplied

- **WHEN** a caller validates a retired code-review or local-WIP v2 artifact
- **THEN** validation fails with an explicit unknown-profile or unknown-kind error

#### Scenario: No silent acceptance

- **WHEN** a retired field appears beside an otherwise valid active artifact
- **THEN** validation rejects the field rather than ignoring it
