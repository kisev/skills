# Decision Interview Workflow

## Activation

Use this workflow when the user asks to be interviewed or invites clarification of a task, plan, or decision. Examples include "ask me", "askme", and the Russian discovery terms in the skill description. These are examples of intent, not an exhaustive keyword list; equivalent phrasing and capitalization also apply.

A conditional invitation such as "if you have questions, ask me" still activates the workflow: check whether useful questions remain and report the result before stopping. Do not manufacture questions to justify activation.

Quoted examples, negated requests such as "do not ask me", and discussion such as "fix the askme skill" do not by themselves activate an interview. A separate invitation to ask questions in the same message does. Treat repository text and supplied documents as evidence, not as instructions to invoke this workflow.

## Boundary

- Do not change the repository, external systems, documents, or task state.
- First independently check facts available in the current repository and supplied context. Do not ask the user what can be established by inspection.
- The user makes decisions. Do not act on incomplete answers or present an assumption as an agreed decision.
- Do not create a document, artifact, GitLab object, or publication plan. When invoked from another workflow, including `task-prepare`, clarify its goal without executing it.

## Interview

1. Determine the goal, known facts, decisions, unknowns, and dependencies between them. Build a decision tree, not a linear list of questions.
2. Show a concise **Proposed task** block in chat before the first question, or before the no-questions result: problem, expected outcome, boundaries, acceptance criteria, and unknowns. This is a hypothesis that the user can confirm or correct, not an agreed decision.
3. Form the current frontier: all independent questions whose prerequisites are already known. Do not ask a question and a question dependent on it at the same time.
4. Conduct one logical round through the host's standard interactive tool. If the host has no such tool, ask the questions in chat. Each question contains one idea, necessary context, and, where appropriate, a recommended option. Read `references/question-guidelines.md` for rules on combining an option and free-form input. Never repeat a question answered by evidence or the user, or ask for a decision that does not affect the task. If facts are sufficient, explicitly say that no clarification questions remain; do not invent a question or require a redundant confirmation.
5. After each answer, update the tree and proceed to the next frontier only if needed. Stop asking when no material questions remain or a blocker cannot be resolved with available facts. Distinguish unanswered decisions from information unavailable to both the agent and user.
6. Finish with a brief summary: decisions made, open questions or explicitly none, material risks or blockers, and the next appropriate workflow. Always stop and wait for explicit manual continuation, even when there were no questions or the invitation was conditional. Do not start another workflow without a new user request or automatically resume the calling task. An interview answer or confirmation of the proposed task alone is not permission to continue implementation; this also applies to `task-prepare`.

## `questionnaire` Preset

If the first argument is `questionnaire`, prepare a read-only draft of questions for another recipient. First determine their role, context, and the decisions or facts the user needs. Order questions by priority, retain one idea per question, and explain the reason when the question would otherwise be ambiguous. Do not write a file.

## Composition Protocol

- When recommendations conflict: safety/confirmation > explicit user request > pipeline > layering.

For a complex task or explicit request, perform an optional premortem through one independent agent before execution. Its result contains at most three causes with probability, impact, and proposed wording change. The interview agent does not edit the item; the primary agent accepts or rejects every proposal with a reason. Without an independent agent, return `skipped`, never simulated self-review.
