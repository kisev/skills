# 08 Crosscutting Concepts

## Purpose

Define target-state mechanisms and policies shared by multiple building blocks.

## Included

- Identity, authentication, authorization, sensitive-data lifecycle, isolation, and auditability.
- Error handling, configuration, observability, persistence, consistency, concurrency, localization, and other genuinely crosscutting mechanisms.
- Direct links from each mechanism to the `REQ-*` entries it provides.

## Excluded

- External trust actors, network placement, measurable quality thresholds, component-local utilities, generic best-practice checklists, and implementation tasks.

## Decomposition Rules

This `README.md` is the concept index and shared summary. Add one file only for a principle or mechanism that affects several building blocks; keep local behavior with its owning block.

## Expected Structure

For each applicable concept, define scope, invariants, participating blocks, data lifecycle or failure behavior, and requirement links. Explain material inapplicability briefly instead of creating empty checklists.

## Content Template

Replace this guidance with indexed shared mechanisms, including applicable identity, authorization, sensitive-data lifecycle, isolation, auditability, errors, configuration, persistence, and observability contracts.
