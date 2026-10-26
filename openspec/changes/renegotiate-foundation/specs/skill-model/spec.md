# Spec Delta

## Purpose

Defines what skills and commands are in this project, which hosts are
supported, and the contracts a skill author must hold: source
self-sufficiency, guidance-style texts, and explicit families.

## ADDED Requirements

### Requirement: Skill and command semantics follow the hosts

Skill and command semantics SHALL follow the Agent Skills open standard and
the canonical documentation of the supported hosts: a skill is packaged
knowledge and ability that the agent loads on demand; a command is a
human-facing entry point.

#### Scenario: Contextual invocation

- **WHEN** a situation matches a skill's description
- **THEN** the agent may load and apply the skill without the user naming it

#### Scenario: Command entry

- **WHEN** a user invokes a command
- **THEN** the host runs the command surface bound to that skill

### Requirement: Three first-class hosts

Every published skill MUST be compatible with and correctly wired for all
three supported hosts — Codex, Claude, and OpenCode — covering discovery
location, format, and invocation knobs.

#### Scenario: Install on any host

- **WHEN** the installer installs a skill for a supported host
- **THEN** the host discovers the skill with its name, description, and
  invocation semantics intact

### Requirement: Commands are optional

A skill MUST declare whether it exposes a human-facing command; the default
is no command. Not every skill needs a command.

#### Scenario: Skill without a command

- **WHEN** a skill whose knowledge is only agent-invoked is installed
- **THEN** no command appears in the host's command list

### Requirement: Authored sources are self-sufficient

Every file a skill's entrypoint references MUST exist in the authored tree,
and authored sources MUST NOT contain build artifacts such as bytecode
caches. A skill runs from a plain checkout without a build step.

#### Scenario: Running from a checkout

- **WHEN** a skill script is executed from the authored tree
- **THEN** it runs without a prior build step

#### Scenario: No build artifacts in sources

- **WHEN** an authored skill tree is inspected
- **THEN** it contains no bytecode caches or other build outputs

### Requirement: Skill texts are guidance, not step-contracts

Skill texts SHALL be guidance for judgment; mechanical strictness and
deterministic logic live in runtime tools the skill invokes, not in
imperative step-by-step textual contracts.

#### Scenario: Mechanical work goes to a runtime

- **WHEN** a step requires deterministic computation or validation
- **THEN** the skill directs the agent to call a runtime tool rather than
  reproducing the procedure in text

### Requirement: Families are explicit

Skill families (skills sharing a name prefix) MUST be declared explicitly in
the skills relation contract. Only family members MAY depend on each other;
every skill outside a family MUST remain self-sufficient and valuable on its
own.

#### Scenario: Family dependency

- **WHEN** a skill belongs to a family and requires a sibling
- **THEN** the relation contract records both the dependency and the family
  membership

#### Scenario: Standalone value

- **WHEN** a non-family skill is installed alone
- **THEN** it remains fully usable
