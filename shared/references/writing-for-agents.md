# Writing for agents

How to word material an agent consumes: a skill line, an `AGENTS.md` rule, a
pointer to a reference document. The packaging differs; the levers are the
same, and they all serve one outcome: the agent taking the same process every
run. `agents-md` applies this reference when wording rules and pointers;
`skill-doctor` and `goal` apply its named diagnoses to their findings.

## Pointers

A pointer is a line in always-loaded material that names out-of-context
content and states the condition for reaching it. The wording, never the
target, decides when the agent reaches the material, so a must-have target
behind a weakly worded pointer is a variance bug: sharpen the wording first,
and inline the material only if sharpening fails.

A pointer states what the material is and lists the branches that trigger
reaching it, where a branch is a distinct case that takes a different path
through the document. Because every word of an always-loaded pointer is paid
on every turn:

- Front-load the leading word: the pointer does its triggering work at its
  start.
- One trigger per branch. Synonyms that rename a single branch are one branch
  written twice; collapse them and keep only genuinely distinct branches.
- Cut what the body already carries; the pointer earns its place by routing,
  not by summarizing.

## The two loads

Every line spends one of two budgets. Context load is the cost of
always-loaded material on the agent's window, paid whether or not it fires.
Cognitive load is the cost on the human of knowing which documents exist and
when to reach for each; the human is the index, and this load is the price of
human agency, spent where judgement matters and removed where it does not.
Material reached only through a pointer escapes context load at the price of
the pointer's line; material with no pointer rides entirely on cognitive load.

## The environment is a source of truth

Package manifests, task graphs, configuration files, directory layout, and
`--help` output are environment facts an agent can look up. A document that
restates them is a cache: a copy of a lookup that earns its load only when the
lookup is expensive. Cache what the agent cannot find by looking, such as the
unwritten convention, the reason behind a choice, or the gotcha no config
confesses; leave one-file, one-command lookups to the environment, where they
cannot go stale. When a cached restatement drifts from the environment, the
environment wins and the cache line is removed, not corrected in place.

## Completion criteria

Every step ends on a completion criterion: the condition that tells the agent
the step is done. Two properties make the criterion a lever:

- Clarity: the agent can tell done from not-done. A vague bound invites
  premature completion, the failure of ending a step before it is genuinely
  done while attention has already moved to being done. Diagnose it whenever
  claimed done coexists with a visible remaining step; defend by sharpening
  the bound first, and only when the bound is irreducibly fuzzy and the rush
  is observed, hide the later steps by splitting the sequence across a real
  context boundary.
- Demand: the wording forces the legwork. "Every modified file accounted for"
  makes the agent dig where "produce a change list" does not; the demand lives
  in the wording, not as a separate step.

The strongest criteria are both checkable and demanding.

## The no-op test

Hunt no-ops sentence by sentence: an instruction the model already obeys by
default pays load to say nothing. The test asks whether the line changes
behavior versus the default, and the answer is settled by running the
document, not by debate: two people who disagree about a no-op disagree about
the default, and a run settles it. When a sentence fails the test, delete the
whole sentence rather than trimming its words.

## Sediment

Sediment is the accumulation of stale layers that settles because adding feels
safe and removing feels risky, until finding the live content means coring
down through the dead weight of it. Diagnose sediment whenever a document
grows by accretion: lines that lost relevance by going stale, branches that
moved behind pointers and left corpses inline, restatements of environment
facts that have since changed. The cure is a relevance pass over every line,
keeping only what still bears on what the document does.

## Source

This reference adapts the writing-for-agents skill authored by Matt Pocock,
published in `openchamber/openchamber@d1fc27c86f258436e2ac748204e8db9bc9c2878f`
(MIT, Copyright (c) 2025 Bohdan Triapitsyn); the pinned revision is recorded in
each skill's frontmatter `metadata.inspired-by` field. This document is an
original adaptation of that idea for this collection, not a copy of the
upstream text.
