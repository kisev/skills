# Constraints

## Purpose

Record externally imposed mandatory constraints that narrow permissible solutions.

## Included

- Required runtime, platform, infrastructure, technology, law, policy, standards,
  and organizational boundaries whose authority is outside the solution design.

## Excluded

- Chosen architecture, internally selected technologies, preferences without
  normative force, behavior, quality targets, architectural consequences, risks,
  or technical debt.

## Decomposition Rules

In v1, keep all constraints in this `README.md`. Automatic splitting is prohibited.

## Expected Structure

```text
constraints/
└── README.md
```

## Content Template

Use stable `REQ-C-NNN`, name the external authority or basis for each constraint, and add verification where it is not obvious. Architecture section 02 references these IDs and explains consequences without restating the constraint.
