# `code-simplify`

## Purpose

Keep code necessary: a passive prevention ladder while coding; on an explicit
request, a report-only audit of a requested scope with ranked, tagged, one-line
findings plus a debt-marker registry.

## Triggers and Near-Misses

Trigger for code simplification and explicit complexity-audit requests;
near-misses: text simplification belongs to `asd-ste100`, `humanize`, and
`eli5`, a merge-request review routes to `code-review`, and a specification
audit routes to `spec-manage`.

## Inputs and Outputs

Input is the code being written or changed, or one explicitly requested audit
scope. Output is silent prevention while coding, or a conversation report of
ranked one-line findings; no files change.

## Workflow Stages

While coding, apply the ladder — necessity, existing code, standard library,
native platform, installed dependency, one line, minimum — to the current
change only, without scanning any repository; a targeted caller search by
exact name for the code being changed is part of the change, and a conscious
cut records a `SIMPLIFY: <ceiling> -> <trigger>` marker on the added or
changed code in the same edit. On an explicit request, agree on the scope,
search usages including dynamic references before any delete, rank findings,
collect markers into a separate registry section, and report.

## Dependencies

The shared `simplification-criteria.md` contract materialized into the skill
archive and the requested scope.

## Remote/Local Effects

Local reading of the requested scope only; no external or write effects.

## Errors, Partial, Escalation

An ambiguous scope triggers one short question before reading anything; an
unresolved dynamic reference blocks a `delete` finding, and a safety-floor
disagreement is reported as a question instead of a finding.

## Unique Constraints

The audit is report-only. No simplification may cross or weaken a trust
boundary, risk data loss, weaken security or accessibility, cancel a
clarification or confirmation gate, or remove behavior the user explicitly
requested. The marker obligation binds only code the current diff adds or
changes; markers on pre-existing code stay pre-existing debt, never findings.

## Requirement

### REQ-F-560 - Keep code necessary and simplification report-only

The skill shall apply the prevention ladder silently to the code being written
or changed without scanning the repository, search callers of an edited
function by its exact name as part of the change, and record a SIMPLIFY debt
marker with its ceiling and upgrade trigger on consciously cut code in the
same edit. It shall audit only on an explicit request inside the requested or
agreed scope. Findings shall be ranked by expected benefit, one line each, and
shall carry the exact location and exactly one tag of `delete`, `stdlib`,
`native`, `reuse`, `yagni`, or `shrink` after a usage search including dynamic
references before any `delete`; markers in the scope shall be reported as a
separate registry section, never as findings, with unfired triggers marked
`no-trigger`. The skill shall never change files, shall never cancel a
clarification or confirmation gate, and shall never propose a simplification
that crosses a trust boundary, risks data loss, weakens security or
accessibility, or removes explicitly requested behavior.

#### Verification

`tests/test_stage20_verification.py` covers the bilingual trigger and
near-miss pairs and the audit pairs; structural checks verify that the shared
simplification criteria materialize into the consuming skill archives.

## Example

`code-simplify` keeps a new date helper to one standard-library call while the
change is written, and on an explicit audit of one module reports ranked
one-line `stdlib`, `reuse`, and `delete` findings after a dynamic-reference
search, changing no file.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
