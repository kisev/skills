# Interface requirements

## Purpose

Describe the system's external interaction surfaces and their normative semantics.

## Included

- Public CLI, API, configuration, and event contracts.
- Commands, fields, messages, ordering, validation, protocol errors, versioning,
  and compatibility semantics at those external surfaces.
- References to formal schemas and declarations.

## Excluded

- Transport-independent behavior owned by `REQ-F-*`, quality thresholds,
  internal module interfaces, future potential interfaces, or complete copies of
  OpenAPI, JSON Schema, or CLI declarations.

## Decomposition Rules

This README is the overview and index. An additional file is allowed only for a real external surface: one interface per file, for example `cli.md` or `http-api.md`.

## Expected Structure

```text
interfaces/
├── README.md
└── <existing-interface>.md
```

## Content Template

List real external surfaces and related `REQ-I-*`. Each additional file states its source of truth, protocol semantics, errors, compatibility, and invariants, and links transport-independent behavior instead of repeating it. If there are no external interfaces, explain that instead of creating files.
