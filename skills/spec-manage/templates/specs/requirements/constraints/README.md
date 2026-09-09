# Constraints

## Purpose

Record mandatory constraints that narrow permissible solutions.

## Included

- Required runtime, platform, and infrastructure; compatibility and policy constraints; required technologies and operational boundaries.

## Excluded

- Preferences without normative force, architectural consequences, risks, or technical debt.

## Decomposition Rules

In v1, keep all constraints in this `README.md`. Automatic splitting is prohibited.

## Expected Structure

```text
constraints/
└── README.md
```

## Content Template

Use stable `REQ-C-NNN`, the basis for each constraint, and verification where it is not obvious. Architecture section 02 references these IDs and explains their consequences.
