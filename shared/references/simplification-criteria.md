# Simplification criteria

Shared criteria for keeping code necessary. `code-simplify` applies them as a
passive prevention ladder while coding and as the report-only audit contract on
an explicit request. The `code-review` panel passes this file into every critic
and arbitrator task; complexity candidates there follow the full finding
contract. These criteria extend the necessity and completion doctrine and never
override it.

## Prevention ladder

Apply the ladder, in order, to the code being written or changed, and stop at
the first step that satisfies the current agreed need:

1. Necessity: the code serves an agreed requirement with a reachable scenario.
2. Existing code: reuse or extend what the repository already provides.
3. Standard library: prefer the standard library of the language or runtime.
4. Native platform: prefer an already available language or platform capability.
5. Installed dependency: prefer an already installed dependency over a new one.
6. One line: prefer the smallest expression that satisfies the need.
7. Minimum: keep whatever remains at its minimum working size.

The ladder is preventive and passive. It applies to the current change only; it
never authorizes scanning a repository, unrelated files, or other people's
code, and it never expands the agreed task. A targeted mechanical search for
callers of a function the current change edits, by its exact name, is part of
that change and is not repository scanning.

### Root cause before a smaller fix

When a simplification edits a function, search its callers by the exact name
before finalizing the change. When updating a caller is the smaller diff that
keeps the behavior correct, fix the cause in the same change instead of
shimming around the call site. The search is targeted and mechanical; it
promises no completeness, and only the audit's usage check covers dynamic
references.

### Debt markers on conscious cuts

When the agreed need is met while earlier ladder steps stay unsatisfied — the
change consciously leaves known debt — record it as part of the same edit: a
one-line marker comment on the added or changed code in the form
`SIMPLIFY: <ceiling> -> <trigger>`, where `<ceiling>` names the accepted
limitation and `<trigger>` names the observable condition that should upgrade
the code, such as a threshold, scenario, or count. For example:
`// SIMPLIFY: linear scan -> index the profiles once they exceed 1,000`.

The marker obligation binds only code the current diff adds or changes. A
missing, outdated, or `no-trigger` marker on pre-existing code is pre-existing
debt under the necessity doctrine: it is never a new finding and never a
`minimum_fix`. The one-line finding contract is unchanged; markers are a debt
registry, not findings.

### Proportionate verification

After a simplification, size new verification to the remaining logic: logic
whose correctness is not evident from a reachable scenario gets one runnable
check; a trivial one-line change gets none. This never removes or weakens an
existing check or gate; it only sizes new verification for the simplified
code.

## Audit contract

An audit runs only on an explicit request and only within the explicitly
requested or agreed scope. It is report-only: it never edits, deletes, moves,
or reformats anything. Findings are ranked by expected benefit, one line each,
and every finding carries:

- the exact location: path plus symbol or lines;
- exactly one tag from the list below;
- the concrete simpler alternative that preserves behavior.

A candidate without a usable alternative is not reported.

### Tags

- `delete`: unreachable, unused, or redundant code that can be removed.
- `stdlib`: replaceable by a standard-library facility of the language or runtime.
- `native`: replaceable by a platform or language capability already available to the project.
- `reuse`: duplicates existing repository code; name the code to reuse.
- `yagni`: speculative generality without a reachable scenario or user consequence.
- `shrink`: correct but oversized; a materially smaller form keeps the behavior.

### Usage check before any delete

Before reporting a `delete` finding, search every usage of the code, including
dynamic references: string-built names, reflection, re-exports, configuration,
templates, generated code, and callers inside the audited scope. An unresolved
dynamic reference blocks the finding.

### Debt-marker registry

An audit also collects the `SIMPLIFY` markers inside the requested scope into
a separate report section, never into the findings: one line per marker with
the exact location, the ceiling, and the trigger. A marker whose upgrade
trigger has not fired is marked `no-trigger` and needs no action; a fired
trigger is reported in the same section as a question for the user's
decision. A missing or outdated marker on pre-existing code stays pre-existing
debt under the necessity doctrine.

## Safety floor

Never propose a simplification that:

- crosses or weakens a trust boundary, or removes validation of untrusted input;
- removes or weakens authentication, authorization, or another security control;
- risks data loss or corruption of persisted state;
- removes an accessibility affordance;
- drops error handling in a way that hides failures;
- cancels, bypasses, or answers on behalf of a clarification or confirmation
  gate.

Behavior that the user explicitly requested is never simplified away; report a
disagreement as a question instead of applying it. This skill never cancels a
clarification or confirmation gate: when a rule or contract requires the
user's decision, the work stops until it is made.

## Complexity in reviews

Review critics treat an oversized or duplicating mechanism as an ordinary
candidate: complete finding fields, a `minimum_fix` that is itself correct and
minimal, and the necessity doctrine's separation of pre-existing debt from the
current change. The arbitrator verdicts every complexity candidate, and a
refuted candidate keeps its verdict visible like any other candidate. Debt
markers follow the same separation: a marker on the current change is the
author's recorded ceiling, and a missing or outdated marker on pre-existing
code is pre-existing debt that never becomes a new finding or a
`minimum_fix`.
