# Quality requirements

## Purpose

Record measurable or verifiable system quality attributes.

## Included

- Performance, reliability, security, usability, and maintainability properties.
- Conditions, load, metrics, allowed thresholds, and verification criteria.

## Excluded

- Functional behavior, interface semantics, externally imposed constraints,
  general wishes without a way to verify them, architectural mechanisms, and
  improvement backlog.

## Decomposition Rules

In v1, keep all quality requirements in this `README.md`. Automatic splitting is prohibited.

## Expected Structure

```text
quality/
└── README.md
```

## Content Template

Use stable `REQ-Q-NNN` and state context, metric or observable property, target, and verification. This file owns measurable security and reliability properties; architecture sections 08 and 10 link them when describing mechanisms. Use ISO/IEC 25010 only as a checklist; do not claim compliance.
