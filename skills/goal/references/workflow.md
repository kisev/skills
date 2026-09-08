# Goal

Read `references/work-item-contract.md` and formulate a goal that can be copied to another system. This skill is strictly read-only: do not create or modify files, XDG state, the repository, session, receipts, or external systems. OpenChamber Goal Mode as an external means of executing a goal is not part of this skill.

## Research

First investigate available facts: the user's request, open files, repository state, available checks, and explicitly named constraints. Do not present an assumption as a fact; place unknowns in `unresolved_questions` or a blocker. Ask through native Question only questions whose answers change the problem, outcome, scope, acceptance criteria, dependency, safety, or stop condition. If facts are sufficient, ask no questions.

For a complex task or explicit request, perform one optional independent premortem before the final wording: at most three risks with probability, impact, and a proposed wording correction. The premortem agent does not edit the item; the primary agent decides each risk. If an independent agent is unavailable, premortem status is `skipped`; after an independent pass, it is `completed`. Do not simulate self-review.

## Output Contract

Output one compact, ready-to-copy JSON object exactly `work-item/v1`, with no additional fields, Markdown wrapper, or service text. It must contain `contract_version`, `item_id`, `problem`, `outcome`, `acceptance_criteria`, `scope.in_scope`, `scope.non_goals`, `dependencies`, `external_actions`, `assumptions`, `safety.constraints`, `safety.operational_constraints`, `risks`, `unresolved_questions`, and `stop_conditions`. Every criterion contains a verifiable `statement`, at least one concrete `evidence`, and `dependencies` references; dependencies form a DAG. Explicitly include result verification and report format in `acceptance_criteria`: brief status (`completed`/`blocked`), facts/evidence for every criterion, checks, unresolved items, and the next safe step. Do not include an acceptance criterion that cannot be verified.

A ready item has at most 3000 characters, verdict `ready`, and empty `unresolved_questions` for blocking questions. If a required fact is unknown, return the same complete `work-item/v1` item with `unresolved_questions` and a stop condition that makes the blocker explicit; do not fill unknowns with invented data. A repeated call with the same facts and input must produce byte-for-byte identical JSON: stable `item_id`, array order, and compact JSON are mandatory. Machine rules may be checked through materialized `scripts/work_item.py validate`, but this does not permit writing state or turn semantic assessment into a machine heuristic.
