# Adaptive interview

The interview closes semantic gaps rather than reproducing a fixed questionnaire.

## Process

1. Collect known facts and decisions.
2. Identify assumptions, gaps, and contradictions.
3. Ask one to five of the most important related questions through the host's native interactive mechanism; if unavailable, ask in chat.
4. Analyze answers and repeat until the target state is unambiguous.
5. Before preview, perform a readiness check in context; do not create a checklist or other repository artifact.

Do not ask what follows reliably from evidence or previous answers. Focus especially on edge cases, failure behavior, compatibility, unsupported behavior, invariants, security boundaries, and lifecycle/state transitions.

## Readiness check

The interview is ready for preview only when: material contradictions are resolved or explicitly retained as `UNKNOWN` by the user; critical unknowns about behavior, architecture, compatibility, security, and quality are absent or explicitly accepted as specification boundaries; scope and explicit non-scope are defined; main behaviors, failure behavior, invariants, and unsupported behavior are unambiguous; external interfaces and compatibility guarantees are defined or explicitly inapplicable; verification of nontrivial normative requirements is understood; architecture, runtime, and deployment are described enough for a consistent target state; and terminology has no material unresolved interpretations.

If any condition is not met, continue the adaptive interview. Do not use the readiness check as a fixed user questionnaire or show a service checklist instead of substantive questions.

## Greenfield interview areas

Cover applicable areas: problem, goal, users, stakeholders, scope, explicit non-scope, key behavior, external interfaces, constraints, compatibility, quality attributes, security, architecture, integrations, runtime, deployment, verification, risks, and terminology.

For an inapplicable area, record a brief reason in the corresponding canonical document. Do not invent content merely to fill a section.
