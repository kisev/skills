# Functional Requirements

## Normative Requirements

### REQ-F-001 - Expose the verified capability surface

The repository shall expose exactly the public inventory in
`evals/contracts/public-surfaces.json`: 29 skills, 33 commands, 6 agents, 3
selectable plugins, and 5 package tools.

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

### REQ-F-004 - Materialize direct Git distribution

The distribution shall install self-contained skill material directly from Git
for supported hosts without depending on a separate runtime package.

### REQ-F-005 - Archive owned retired assets

When exact-owned retired assets are reconciled, the system shall archive them
content-addressably and preserve unrelated user-owned files and durable state.
Human reconcile preview shall be blocked, without an Apply command, when
`modified_managed` or `conflicts` is non-empty; it shall list every blocking path
and provide remediation. Clean preview shall retain the digest and exact Apply
command contract.

### REQ-F-006 - Manage package-owned profiles safely

Profile mutations shall use preview and confirmed apply phases, exact ownership,
atomic rollback, and restart semantics defined by the package contract.

### REQ-F-007 - Provide observational health and inventory

The package shall expose capability and doctor observations without installing,
repairing, or mutating runtime state.

### REQ-F-008 - Support compatible host integration

The package shall support the declared OpenCode compatibility range and expose
the package tools, plugin exports, and CLI behavior defined by the package
contract.
