# Functional Requirements

## Normative Requirements

### REQ-F-001 - Expose the verified capability surface

The repository shall expose exactly the public inventory in
`evals/contracts/public-surfaces.json`: 27 skills, 27 commands, 6 agents, 3
selectable plugins, and 1 package tool.

#### Verification

Compare the contract with `skills/`, `packages/opencode/src/catalog.ts`, and
generated package assets; execute the public inventory tests.

### REQ-F-002 - Route work through bounded orchestration

When an OpenCode task is dispatched, the package shall resolve an eligible host
agent and require a one-use receipt bound to task, requirements, card, revision,
and expiry before execution.

### REQ-F-003 - Preserve useful partial results

When required evidence is missing, stale, malformed, or contradictory, a
workflow shall return a structured `partial`, `blocked`, or `error` outcome and
shall identify the missing evidence and safe escalation.

### REQ-F-004 - Publish one verified release

On a validated release tag, CI shall pass the complete quality gate before any
publication, build the exact tagged Pages distribution and one exact npm tarball,
and bind both to one release manifest. CI shall verify deployed Pages bytes, npm
integrity, signatures, provenance, imports, and CLI before creating the GitHub
Release. The distribution version and source revision shall match the immutable
tag, and a rerun shall accept only identical previously published bytes.

### REQ-F-005 - Archive owned retired assets

When exact-owned retired assets are reconciled, the system shall archive them
content-addressably and preserve unrelated user-owned files and durable state.
Reconcile shall inspect and mutate only package-owned OpenCode assets; portable
skill trees and installer lock files shall not affect its classifications, plan,
digest, conflicts, or operations. Portable skill updates and removals remain
owned by the `skills` CLI.
Human reconcile preview shall be blocked, without an Apply command, when
`modified_managed` or `conflicts` is non-empty; it shall list every blocking path
and provide remediation. An actionable clean preview shall retain the digest and
exact Apply command contract; a no-op preview shall issue no receipt or Apply
command. Every new dry-run in one project or global scope shall
supersede the previous unconsumed receipt across installer, reconcile, profile,
and critic domains; deterministic plan and unique confirmation digests are
separate, and superseded confirmation fails closed.

### REQ-F-006 - Manage package-owned profiles safely

Profile mutations shall use preview and confirmed apply phases, exact ownership,
atomic rollback, and restart semantics defined by the package contract.

### REQ-F-007 - Provide observational health and inventory

The direct CLI shall expose capability and doctor observations without installing,
repairing, or mutating runtime state.

### REQ-F-008 - Support compatible host integration

The package shall support the declared OpenCode compatibility range and expose
the route tool, plugin exports, and CLI behavior defined by the package
contract.
