# Decision Interview Workflow

Do not change the repository, external systems, documents, task state, or create artifacts, GitLab objects, or publication plans. First verify facts available in the repository and supplied context; do not ask what inspection can establish. The user makes decisions: never act on an incomplete answer or present an assumption as an agreed decision. When invoked from `task-prepare`, agree the task meaning first, then return to that workflow.

Build a decision tree of the goal, known facts, decisions, unknowns, and dependencies. Before the first question, show a **Proposed task** containing problem, expected outcome, boundaries, acceptance criteria, and unknowns; it is a hypothesis the user may correct. Ask only the current frontier: independent questions whose prerequisites are known. Never ask a question together with one dependent on it.

Run one logical round through the host interaction mechanism, or in chat when unavailable. Each question contains one idea, required context, and a recommended option when useful. Read `references/question-guidelines.md` for option/free-text rules. If facts suffice, ask only to confirm the proposed task. Update the tree after every answer and stop at shared understanding or an evidence-blocked question. Finish with decisions, open questions, risks, and the next suitable workflow. Do not start it without a new request, except that confirmed meaning lets the calling `task-prepare` continue without creating or changing an issue.

With first argument `questionnaire`, prepare a read-only question draft for another recipient: establish role, context, and needed decisions/facts; prioritize questions; keep one thought per question; explain ambiguous questions; do not write a file. For complex work or an explicit request, one independent premortem may supply at most three causes with probability, impact, and proposed wording change. The interviewer does not edit the item; the primary agent accepts or rejects each proposal with a reason. Without an independent agent, return `skipped`, never simulated self-review.

## Boundary

- Do not modify the repository, external systems, documents, or task state.
- First independently check facts available in the current repository and supplied context. Do not ask the user what can be established by inspection.
- The user makes decisions. Do not act on incomplete answers or present an assumption as an agreed decision.
- Do not create a document, artifact, GitLab object, or publication plan. When invoked from `task-prepare`, first agree the task's meaning, then proceed to its workflow.

## Interview

1. Determine the goal, known facts, decisions, unknowns, and dependencies between them. Build a decision tree, not a linear list of questions.
2. Before the first question, show a **Proposed Task** block in chat: problem, expected outcome, boundaries, acceptance criteria, and unknowns. This is a hypothesis that the user can confirm or correct.
3. Form the current frontier: all independent questions whose prerequisites are already known. Do not ask a question and a question dependent on it at the same time.
4. Conduct one logical round through the host's standard interactive tool. If the host has no such tool, ask the questions in chat. Each question contains one idea, necessary context, and, where appropriate, a recommended option. Read `references/question-guidelines.md` for rules on combining an option and free-form input. If facts are sufficient, ask only for confirmation of the proposed task.
5. After the answer, update the tree and proceed to the next frontier. Stop when shared understanding is reached or a blocker remains that cannot be resolved with available facts.
6. Finish with a brief summary: decisions made, open questions, risks, and the next appropriate workflow. Do not start another workflow without a new user request. Exception: if `task-prepare` initiated this interview, confirmation of the proposed task permits it to continue the current workflow, but not to create or modify a GitLab issue.

## `questionnaire` Preset

If the first argument is `questionnaire`, prepare a read-only draft of questions for another recipient. First determine their role, context, and the decisions or facts the user needs. Order questions by priority, retain one idea per question, and explain the reason when the question would otherwise be ambiguous. Do not write a file.

## Composition Protocol

- When recommendations conflict: safety/confirmation > explicit user request > pipeline > layering.

For a complex task or explicit request, perform an optional premortem through one independent agent before execution. Its result contains at most three causes with probability, impact, and proposed wording change. The interview agent does not edit the item; the primary agent accepts or rejects every proposal with a reason. Without an independent agent, the result is `skipped`; do not simulate self-review.
