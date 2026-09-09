# Interface requirements

## Purpose

Describe the system's external interaction surfaces and their normative semantics.

## Included

- Public CLI, API, configuration, and event contracts.
- Compatibility guarantees, validation, errors, and references to formal schemas and declarations.

## Excluded

- Internal module interfaces, future potential interfaces, or complete copies of OpenAPI, JSON Schema, or CLI declarations.

## Decomposition Rules

This README is the overview and index. An additional file is allowed only for a real external surface: one interface per file, for example `cli.md` or `http-api.md`.

## Expected Structure

```text
interfaces/
├── README.md
└── <existing-interface>.md
```

## Content Template

List interfaces and related `REQ-I-*`. Each additional file states its source of truth, semantics, errors, compatibility, and invariants. If there are no external interfaces, explain that instead of creating files.
