# verification Workflow

Portable completion discipline: **no completion claims without fresh
verification evidence**. Evidence comes from a command you ran in the current
session, not from memory, hope, or another agent's report.

## Scope and precedence

This skill is the portable floor for any environment. Inside a repository
that defines its own verification contracts — a task graph, release gates, a
contribution checklist — those local contracts take precedence and this skill
defers to them: run the local gate, and do not restate or re-derive it. The
skill never invents verification commands for a project; it forces the one
you already have to actually run before claims are made.

## The gate

Before any claim about the state of the work:

1. **Identify** the command whose output proves this specific claim.
2. **Run** it now, fresh and complete — not a cached or partial variant.
3. **Read** the full output: exit code, failure counts, warnings.
4. **Verify** the output actually confirms the claim.
5. **Report** actual status: with evidence when confirmed, with the real
   status and the failing evidence when not.

Skipping any step turns the claim into a guess. An unsuccessful or
unrunnable verification is reported as exactly that, with the command and its
error, and the work stays open.

## What claims require

| Claim | Fresh evidence required | Never sufficient |
| - | - | - |
| Tests pass | Test command output: zero failures | An earlier run, "it should pass" |
| Build succeeds | Build command: exit 0 | Linter output alone |
| Bug fixed | The original failing scenario now passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle observed | One green run |
| Agent task done | The repository diff inspected by you | The agent's success report |
| Requirements met | Item-by-item check against each | Tests passing |

## Red flags — stop and verify

- Wording like "should", "probably", or "seems to" attached to a success.
- Expressions of satisfaction before any verification command ran.
- About to commit, push, open a merge request, or hand off without a fresh
  gate for the exact delta being declared done.
- Trusting a partial check, an extrapolation, or a delegated agent's
  self-report without looking at the resulting state yourself.
- Reusing evidence from an earlier session or an earlier revision of the
  change; evidence must be fresh for the current state.
- Any phrasing that implies completion while the proving command has not run.

## Rationalizations

| Rationalization | Reality |
| - | - |
| "It should work now." | Should is not evidence; run the command. |
| "I am confident in the change." | Confidence is not evidence; run the command. |
| "The full check is slow; this partial one is close enough." | Partial checks prove nothing about the whole. |
| "The linter passed." | The linter does not compile or run the tests. |
| "The other agent reported success." | Verify the resulting state independently. |
| "Just this once, for a small change." | Exceptions are how stale claims ship; there is no just this once. |
| "Rephrasing it as almost done makes it true." | The rule binds paraphrases and implications, not only exact words. |

When the user explicitly accepts an unverified state, say plainly that the
claim is unverified and what evidence is missing; explicit user decisions
replace the claim, they do not launder it.

## Completion report

State per acceptance criterion: the evidence command, its output summary, and
its status; list the checks that did not run and why. Never declare complete
on partial evidence — report the gap instead. A verified completion can then
route the change to `code-review` before publication.

## Credits

Inspired by `obra/superpowers` (`verification-before-completion`), MIT,
Copyright (c) 2025 Jesse Vincent; the pinned revision is recorded in the
frontmatter `metadata.inspired-by` field. This workflow is an original
adaptation of that idea for this collection, not a copy of the upstream text.
