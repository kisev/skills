# `/code-simplify`

## Purpose

Expose the code-simplify skill as a slash command for coding-time prevention
and explicit simplification audits.

## Triggers and Near-Misses

Routes simplification requests and explicit complexity audits of a stated
scope. Near-misses include prose simplification, merge-request reviews, and
specification audits.

## Inputs/Outputs

An optional argument names the requested audit scope and is passed unchanged.
Output is a ranked report of tagged one-line findings plus a debt-marker
registry; no files change.

## Workflow Stages

Load the skill, pass the explicit scope unchanged, apply the passive ladder or
run the report-only audit, and report without writing.

## Dependencies

`code-simplify` and its materialized simplification criteria.

## Remote/Local Effects

Bounded local read effects only.

## Errors/Partial/Escalation

An ambiguous scope produces one short question and no audit; safety-floor
conflicts are reported as questions instead of findings.

## Unique Constraints

The command loads exactly the code-simplify skill and never executes or
authorizes file changes: applying a finding stays the user's separate decision.

## Requirement

### REQ-I-425 - Route the code-simplify command

The command shall load exactly `code-simplify` and preserve the explicit audit
scope unchanged while keeping every invocation report-only.

## Example

`/code-simplify src/api` audits the requested scope and reports ranked one-line
findings without changing files.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
