# Task Baseline

The task baseline is what the review measures the implementation against. It
comes from GitLab and the human, and it is taken as given.

## Sources

- the linked issues that the merge request closes: title, description, labels,
  and state;
- the merge request description;
- the human's answers in the startup round.

The baseline records the goal, the acceptance criteria, the constraints, and
the open questions. The goal is the central question: does this change solve
the task it was made for?

Never read or assess an OpenSpec change, a specification repository, or a
planning document: OpenSpec is out of scope.

## Confirmation

Present the baseline to the human once together with the OCR model or models
and effort. Record the confirmation or correction before running the review.
This is the only question round; no second round exists.

When the goal cannot be established from the GitLab context or the human's
answer, record it as unknown. The fulfillment verdict then cannot be `solved`.

## Doubts

A gap or contradiction in the task statement is recorded as a doubt, separately
from code findings:

- the ambiguity;
- the possible readings;
- who decides.

The review does not re-plan the task, rewrite the acceptance criteria, or author
a specification. The doubt is reported as a question for the human.

## Collection facts

The baseline may cite collected facts: linked issues, CI status, and unresolved
discussions. A failed collection leaves the corresponding fact unknown, not
empty.
