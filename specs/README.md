# Canonical Specification

## Target

This English-only specification describes the merged target `2.0.0` of the
portable Agent Skills repository. It records supported contracts, not history,
roadmap, or implementation plans.

## Public Surface

The verified public inventory is 29 skills, 33 commands, 6 agents, 3 selectable
plugins, and 5 package tools. The core infrastructure plugin is always
available; selectable plugins are `rules-injector`, `rtk`, and `zed-bell`.

## Navigation

- [Requirements](requirements/README.md) define normative, verifiable contracts.
- [Architecture](architecture/README.md) describes boundaries and runtime views.
- [Capabilities](capabilities/README.md) indexes every public capability.
- [Crosscutting concepts](architecture/08-crosscutting-concepts/README.md) hold shared behavior.
- [Traceability](traceability.json) binds requirements to automated and manual evidence.

## Scope Boundary

The specification covers direct Git distribution, the OpenCode package and CLI,
orchestration, durable state, content-addressed archive behavior, security
boundaries, tests, evals, and compatibility. It does not define repository
quality gates beyond the existing `task check` contract.
