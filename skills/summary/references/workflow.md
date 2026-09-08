# Workflow

Produce an accurate structured summary in the language of the latest user
request; use English when that language is ambiguous. Do not add facts absent
from the source data or perform new research instead of processing them.

## Boundary and output

- By default, return the summary in chat. Create a file only on explicit request,
  after previewing its path and complete content.
- Read large source files in parts, but cover all content rather than only the
  beginning.
- Retain all substantive content: facts, decisions, tasks, risks, arguments, and
  constraints. Remove greetings, filler words, technical remarks, repetition,
  self-corrections, and immaterial personal details.
- Do not add introductions, conclusions, or service comments to the completed
  minutes.

## Accuracy

- Strictly distinguish the current situation, a proposal, an accepted decision,
  and an assigned task. Do not turn a discussion into a decision or task.
- Preserve confidence level, numbers, versions, dates, deadlines, and
  disagreements. If a value cannot be reliably reconstructed, mark it as needing
  clarification or as unintelligible.
- Correct obvious recognition errors from context and professional terminology,
  but do not guess the meaning of unclear numbers, identifiers, names, or roles.
- Silently remove looping, duplication, phantom spam, isolated unconnected words,
  and joining artifacts. Split joined utterances by meaning.
- Speaker labels are unreliable: reconstruct authorship only with high confidence.
  Do not merge participants' questions, answers, and post-discussion.

## Structure

Choose the structure for the material type.

- For a sync or technical discussion: a meeting-minutes title, followed as needed
  by a brief summary, discussion content, decisions and agreements, tasks and
  next actions, open questions, problems, risks, constraints and dependencies,
  transcription ambiguities, and alternatives and proposals.
- For an interview: candidate and position, answers by topic, strengths, gaps and
  red flags, verdict, and separate post-discussion.
- For a one-on-one: context, work questions and blockers, feedback, agreements,
  and material ambiguities.
- For planning: plan by participant, decisions and shifts, open questions, and
  risks.

Record explicitly assigned actions as
`- [ ] Action - responsible: name/not specified - deadline: date/not specified`.
List ambiguities only when they can change the understanding of a fact, decision,
or task.
