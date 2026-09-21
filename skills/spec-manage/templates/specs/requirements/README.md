# Requirements

## Purpose

Explain that this section contains normative, verifiable agreements for system behavior, interfaces, quality, and constraints.

## Included

- An index of the four requirement types.
- Shared append-only stable-ID, lifecycle-history, and traceability rules.
- Mutually exclusive semantic ownership for the four requirement types.
- References to machine-readable contracts.

## Excluded

- Component structure and runtime flows, implementation plans, task decomposition, or repetition of child requirements.

## Decomposition Rules

Use only the four required type directories. Do not create new top-level types.

## Expected Structure

```text
requirements/
├── README.md
├── functional/README.md
├── interfaces/README.md
├── quality/README.md
└── constraints/README.md
```

## Content Template

Give a short section index. State that `REQ-F-*` owns transport-independent observable behavior, `REQ-I-*` owns an external surface and protocol semantics, `REQ-Q-*` owns measurable or verifiable quality, and `REQ-C-*` owns externally imposed solution limits. One normative fact has one owner; other documents link to it. State that new numbers exceed the historical maximum, active requirements need no status boilerplate, and inactive requirements use the compact lifecycle line below. Remove these instructions from the created document.

```markdown
> Lifecycle: `superseded` | Changed: `YYYY-MM-DD` | Reason: <reason> | Replacement: [REQ-X-NNN](#replacement-heading)
```

Use only `deprecated`, `superseded`, or `withdrawn`. Require the date and reason; require a replacement link for `superseded`, forbid it for `withdrawn`, and include it for `deprecated` only when one exists. Allow active to any inactive status and `deprecated` to `superseded` or `withdrawn`; terminal records are not reactivated.
