# Functional requirements

## Purpose

Record normative observable system behavior and conditions for its verification.
The behavior remains the same regardless of whether it is reached through a CLI,
HTTP API, event, or another transport.

## Included

- User and system behavior.
- Reactions to events and errors.
- Invariants and supported lifecycle transitions.

## Excluded

- External surface syntax and protocol semantics owned by `REQ-I-*`.
- Quality goals, platform constraints, component design, and implementation detail.

## Decomposition Rules

In v1, keep all functional requirements in this `README.md`. Do not automatically split them by features, domains, use cases, or components.

## Expected Structure

```text
functional/
└── README.md
```

## Content Template

For each requirement, use a stable `REQ-F-NNN`, a clear normative statement, optional rationale, and verification when nontrivial. Link interface, quality, or constraint owners instead of repeating their normative facts.

```markdown
### REQ-F-001 - Retry a request

When an external service returns 503, the client shall make no more than three attempts.

#### Verification

- A fourth request is not made.
```
