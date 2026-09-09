# Goal

Read `references/work-item-contract.md` and formulate a goal that can be copied to another system. This skill is strictly read-only: do not create or modify files, XDG state, the repository, session, receipts, or external systems. OpenChamber Goal Mode as an external means of executing a goal is not part of this skill.

## Research

First investigate available facts: the user's request, open files, repository state, available checks, and explicitly named constraints. Do not present an assumption as a fact; place unknowns in `unresolved_questions` or a blocker. Ask through native Question only questions whose answers change the problem, outcome, scope, acceptance criteria, dependency, safety, or stop condition. If facts are sufficient, ask no questions.

For a complex task or explicit request, perform one optional independent premortem before the final wording: at most three risks with probability, impact, and a proposed wording correction. The premortem agent does not edit the item; the primary agent decides each risk. If an independent agent is unavailable, premortem status is `skipped`; after an independent pass, it is `completed`. Do not simulate self-review.

## Output Contract

Internally preserve the normalized `work-item/v1` contract and validate it when
useful, but return structured Markdown rather than JSON. Use only non-empty
sections such as `## Problem`, `## Outcome`, `## Acceptance criteria`,
`## Scope`, `## Evidence`, `## Risks`, `## Open questions`, and `## Stop
conditions`. Keep the result at or below 4000 characters, preserve exact
technical fragments, and include a brief completion/report contract with status,
evidence for every criterion, checks, unresolved items, and the next safe step.
Do not declare complete when required evidence is partial or a blocker remains.

A ready result is non-empty, at most 4000 characters, and has no blocking open
questions. If material conditions do not fit, stop and propose splitting the
request into several goals rather than truncating or hiding them. If a required
fact is unknown, show it as an open question and an explicit stop condition; do
not invent data. Equivalent facts and input must produce stable section and
item ordering. Machine rules may be checked through materialized
`scripts/work_item.py validate`, but this does not permit writing state or turn
semantic assessment into a machine heuristic.
