# Discussion Replies

This contract applies to every reply drafted for a GitLab merge request
discussion. It is self-contained: apply it from this file, no other skill is
required at run time. `clarity-rules.md` is applied alongside it for plain
language; `humanize-patterns.md` is available for an optional final editing
pass, never as a required step.

## Read the whole discussion first

- Read every note in the discussion in order, and the merge request
  description, the linked issues, and the current diff of the files it
  touches. A reply to the last note alone answers the wrong question when the
  thread moved on.
- Answer the latest relevant point first. Add earlier context only when it
  changes that answer; do not restate the thread.
- Address the participant naturally by their GitLab name or role. Do not force
  a pronoun when the name or role reads naturally on its own.
- Stay on the discussion's subject. A separate problem gets a separate note,
  not a paragraph in this reply.

## Write in the user's voice

- Write from the authenticated user's first person and factual role: what they
  did, saw, decided, or need. The reply is the user speaking, not a report
  about the user.
- Do not narrate the user in the third person.
- Do not attribute actions, decisions, promises, plans, or reactions the user
  did not take or state. When the fact is unknown, say it is unknown or ask;
  never fill the gap with a plausible action.
- Do not invent earlier agreement, review approval, intent, or emotion. Quote
  what exists; if it is absent, it stays absent.
- Do not claim tests, checks, or verification the user did not run.

## Keep the reply useful

- State the fact, the reason, or the next step. No code suggestions in the
  reply unless the user asked for one in this discussion.
- Preserve exact tokens: code, commands, paths, IDs, revisions, labels, and
  quotations. Never paraphrase an identifier.
- Answer a direct question directly and completely. If part of it cannot be
  answered, say which part and why.
- When the user disagrees, give the reason; do not soften an agreed fact into
  a preference or a preference into a fact.

## Open and closed discussions

- Open discussions: process all of them; draft a substantive reply wherever
  one is needed.
- Closed discussions: draft a reply only when the problem is still present on
  the current head; pair it with a reopen request. Otherwise leave the thread
  untouched.
- Every reply is published as a draft note first; the user edits and submits
  it in the GitLab interface.

## Final check

Before the reply leaves the draft, verify each line: first person, the facts
and actions only those the user established, the latest relevant point
answered, the exact tokens intact, and no request for an action the user did
not authorize.
