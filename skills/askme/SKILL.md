---
name: askme
description: >-
  Clarify an incomplete task, plan, or design through a dependency-aware
  interview. Use this skill when requirements are incomplete, a design choice
  needs a decision, or a task must be agreed before preparation.
license: MIT
compatibility: Host-provided chat or interactive question tool; no external files or packages required.
metadata:
  author: Kirill Sevriugin
  version: 1.0.0
---

# Clarify the Request

## Boundary

- Do not change the repository, external systems, documents, or task state.
- First inspect facts available in the current repository and supplied context.
  Do not ask the user for facts that can be established by inspection.
- The user makes decisions. Do not treat an assumption as an agreed decision.
- Do not create a document, artifact, tracker object, or publication plan.

## Interview

1. Identify the goal, known facts, decisions, unknowns, and dependencies. Build
   a decision tree rather than a flat list of questions.
2. Before the first question, show a **Proposed task** block with the problem,
   expected result, boundaries, acceptance criteria, and unknowns. Make clear
   that it is a hypothesis the user can correct.
3. Determine the current frontier: all independent questions whose prerequisites
   are known. Do not ask a question and its dependent question together.
4. Run one logical round using the host's standard interactive question tool.
   If the host has no such tool, ask the questions in chat. Each question must
   contain one idea, the necessary context, and a recommended option when
   useful. For option and free-form input rules, read
   `references/question-guidelines.md`.
5. After the answer, update the decision tree and move to the next frontier.
   Stop when there is shared understanding or an unresolvable blocker.
6. Finish with a concise summary of decisions, open questions, risks, and the
   next suitable workflow. Do not start that workflow without a new request.

## Preset `questionnaire`

If the first argument is `questionnaire`, prepare a read-only draft of questions
for another recipient. Establish their role, context, and needed decisions or
facts first. Order questions by priority, keep one idea per question, and
explain why a question is needed when it could be ambiguous. Do not write a
file.
