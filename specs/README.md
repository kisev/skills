# Canonical Specification

## Target

This English-only specification describes the current merged target of the
portable Agent Skills repository. It records supported contracts and compact
lifecycle history for stable requirements and decisions, not a change log,
roadmap, or implementation plans.

## Public Surface

The verified public inventory is 27 skills, 27 commands, 6 agents, 3 selectable
plugins, and 1 package tool. The core infrastructure plugin is always
available; selectable plugins are `rules-injector`, `rtk`, and `zed-bell`.

## Navigation

- [Requirements](requirements/README.md) define normative, verifiable contracts.
- [Architecture](architecture/README.md) describes boundaries and runtime views.
- [Capabilities](capabilities/README.md) indexes every public capability.
- [Crosscutting concepts](architecture/08-crosscutting-concepts/README.md) hold shared behavior.

## Scope Boundary

The specification covers the GitHub Pages distribution, the OpenCode package and CLI,
orchestration, durable state, content-addressed archive behavior, security
boundaries, tests, evals, and compatibility. The `spec-manage` workflow owns
canonical updates and read-only semantic review with an independent critic pass.
