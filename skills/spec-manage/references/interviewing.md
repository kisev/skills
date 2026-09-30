# Adaptive interview

The interview closes semantic gaps rather than reproducing a fixed questionnaire.
Apply `references/question-guidelines.md` throughout this native interview,
including mode, canonical language, scope, and design decisions.

## Process

1. Collect known facts and decisions.
2. Identify assumptions, gaps, and contradictions.
3. Ask the smallest useful round of independent questions with known prerequisites through the host's native interactive mechanism; if unavailable, ask in chat. Related topics are not necessarily independent. If a plausible answer could change another question's necessity, wording, options, or recommendation, ask the prerequisite first and wait. Explain why each choice arose, its practical effects and material risks, and the basis of any recommendation before asking.
4. Analyze actual answers, including non-recommended and custom choices. Recheck changed assumptions against evidence and remove or rewrite invalidated follow-ups before forming the next round. Repeat until the target state is unambiguous; never silently select the recommended branch.
5. Before writing, perform a readiness check in context; do not create a checklist or other repository artifact.

Do not ask what follows reliably from evidence or previous answers. Focus especially on edge cases, failure behavior, compatibility, unsupported behavior, invariants, security boundaries, and lifecycle/state transitions.

## Readiness check

The interview is ready for writing only when: material contradictions are resolved or explicitly retained as `UNKNOWN` by the user; critical unknowns about behavior, architecture, compatibility, security, data lifecycle, and quality are absent or explicitly accepted as specification boundaries; scope and explicit non-scope are defined; each normative fact has one unambiguous `REQ-F-*`, `REQ-I-*`, `REQ-Q-*`, or `REQ-C-*` owner; main behaviors, failure behavior, invariants, and unsupported behavior are unambiguous; external interfaces and compatibility guarantees are defined or explicitly inapplicable; verification of nontrivial normative requirements is understood; applicable direct requirement-to-architecture and requirement/ADR links are known; architecture, runtime, and deployment are described enough for a consistent target state; significant decisions have applicable compatibility, migration, rollback, reversibility, and risk implications understood; trust boundaries, runtime exposure, secret placement, identity, authorization, sensitive-data lifecycle, isolation, auditability, and measurable security/reliability properties have the canonical owners defined by the architecture profile; and terminology has no material unresolved interpretations.

If any condition is not met, continue the adaptive interview. Do not use the readiness check as a fixed user questionnaire or show a service checklist instead of substantive questions.

## Greenfield interview areas

Cover applicable areas: problem, goal, users, stakeholders, scope, explicit non-scope, key behavior, external interfaces, constraints, compatibility, quality attributes, security, architecture, integrations, runtime, deployment, verification, risks, and terminology.

Assess each area for applicability. For an inapplicable material area, record a
brief reason in the corresponding canonical document. Do not produce a readiness
checklist, copy the same concern into several documents, or invent content merely
to fill a section.
