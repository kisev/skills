# Simplified Technical Text Workflow

## Purpose

Check and rewrite technical text in the language of the source so instructions
become unambiguous and mechanical: one action per instruction, direct wording,
consistent terms. The method applies Simplified Technical English principles to
the task's language; it never claims certified ASD-STE100 compliance, because
certification requires the official specification and its verified word lists,
which this skill does not include.

## Principles

- One instruction states one action that one actor performs; split compound
  instructions at their natural seams.
- Prefer the active voice and direct word order where the language allows it
  naturally; do not distort the language to force an English grammar pattern or
  an English word list.
- Keep one term for one object; do not alternate synonyms for the same control,
  part, or action.
- Prefer concrete verbs over nominalizations; keep the text's established
  technical vocabulary instead of popular paraphrases.
- Keep sentences short, normally one or two clauses. A long sentence may stay
  long only when splitting it would change the meaning.
- Keep warnings, notes, conditions, and exceptions logically distinct from the
  steps they qualify.

## Invariants

Apply `references/clarity-rules.md`. A rewrite preserves exactly:

- obligation, permission, and prohibition strength;
- numbers, units, thresholds, and identifiers;
- conditions, exceptions, and boundaries;
- the stated actor of every action;
- the separation of facts, assumptions, and recommendations.

## Method

1. Read the whole text; determine its language, audience, and purpose.
2. Inventory the obligations, conditions, exceptions, numbers, and boundaries
   the text carries. This inventory is the contract the rewrite must preserve.
3. Rewrite only the passages that fail the principles; keep compliant passages
   unchanged. Do not rewrite text that is already clear for the sake of
   rewriting.
4. When information is missing (unnamed actor, unclear order, missing
   parameter), do not invent it: ask one bounded question or mark the gap
   explicitly in place.
5. Verify the result against the step 2 inventory, and report what was
   preserved, what was clarified, and what remains unknown.

## Boundary

- The result follows the principles above; it does not assert conformance to
  the ASD-STE100 standard. If the user needs a certified result, say that the
  official specification and a verified dictionary are required and absent
  here.
- Apply `humanize` when the rewritten text is substantial user-facing prose;
  simplified style must still read naturally in its language.
