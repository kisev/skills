# Canonical Specification

## Canonical Language

Canonical language: English. This repository-specific choice is governed by
[REQ-C-001](requirements/constraints/README.md#req-c-001---english-only-canonical-specification),
not by a universal `spec-manage` language restriction.

## Target

This English-only specification describes the current merged target of the
portable Agent Skills repository. It records supported contracts and compact
lifecycle history for stable requirements and decisions, not a change log,
roadmap, or implementation plans.

## Public Surface

The verified public inventory is 28 skills, 28 commands, 6 agents, 3 selectable
plugins, and 1 package tool. The core infrastructure plugin is always
available; selectable plugins are `rules-injector`, `rtk`, and `zed-bell`.

## Navigation

- [Requirements](requirements/README.md) define normative, verifiable contracts.
- [Architecture](architecture/README.md) describes boundaries and runtime views.
- [Capabilities](capabilities/README.md) indexes every public capability.
- [Crosscutting concepts](architecture/08-crosscutting-concepts/README.md) hold shared behavior.

## Extension Index

- [Capabilities](capabilities/README.md): Public-surface inventory and capability-specific contracts that reference shared requirements and architecture instead of duplicating them.

## Scope Boundary

The specification covers the GitHub Pages distribution, the OpenCode package and CLI,
orchestration, durable state, content-addressed archive behavior, security
boundaries, tests, evals, and compatibility. The `spec-manage` workflow owns
canonical updates and read-only semantic review with an independent critic pass.
