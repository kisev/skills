# Requirements

## Purpose

Explain that this section contains normative, verifiable agreements for system behavior, interfaces, quality, and constraints.

## Included

- An index of the four requirement types.
- Shared append-only stable-ID, lifecycle-history, and traceability rules.
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

Give a short section index and rules for `REQ-F-*`, `REQ-I-*`, `REQ-Q-*`, and `REQ-C-*`. State that new numbers must exceed the historical maximum and retired requirements remain as compact lifecycle records. Remove these instructions from the created document.
