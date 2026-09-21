# Minimum meaningful content

Every required document remains present, but length is not a readiness signal.
Each viewpoint must use at least one of the three forms below. Choose a form from
project evidence; never insert it automatically as a placeholder.

## Confirmed content

State a concrete project-specific target-state fact and link its normative owner
when another canonical document owns the requirement, interface, constraint, or
decision. Name the evidence that supports an onboarded claim when that matters.

Example: `The Importer passes validated records to the Store; it does not open
files. See REQ-F-001. Evidence: src/importer.py and tests/test_importer.py.`

## Inapplicable content

Name the specific project condition that makes this viewpoint or concern
inapplicable. A bare `N/A`, an empty heading, or a generic claim that the project
is small is not sufficient.

Example: `No network deployment topology applies because the distributed
artifact is a local process with no listener or remote runtime dependency.`

## Accepted `UNKNOWN`

Use `UNKNOWN` only when the canonical tree must expose a material knowledge
boundary that the user explicitly accepts. State the unknown fact, its bounded
area and consequence, the evidence needed to resolve it, and the user's explicit
acceptance. Do not infer acceptance or use `UNKNOWN` to avoid investigation.

Example: `UNKNOWN (accepted by the product owner): whether files above 2 GiB are
supported. Boundary: input-size compatibility only; consequence: no size promise
is made. Needed evidence: an agreed limit and stress results.`

These forms define concise content, not weaker readiness. The document profiles,
semantic audit criteria, authority rules, and formal validation remain unchanged.
The compact example in `references/minimal-example.md` illustrates depth only;
do not copy it mechanically or treat it as a normative template.
