# Design

> Capture after the OCR-engine and profile rounds on 2026-11-09. Decisions are
> owner-confirmed unless marked (open). Implementation details that do not
> change the approach are listed under Implementation notes.

## Context

The current skill is one of the heaviest in the repository: `SKILL.source.md`
is 8.1 KB, the 17 authored references are 118 KB, and the built archive is
28 files / 340 KB including a 108 KB JSON schema. The runtime is roughly
23k lines of Python with 37 public subcommands. The primary path is a
one-process `reviewmatic run` with eight authoring stages; a marked
step-by-step repair path and legacy v2 commands remain supported. The
contract test in `apps/reviewmatic/tests/test_skill_contract.py` pins the
runtime command surface, the skill texts, and the documentation map to each
other.

The runtime drifted from its purpose. It was meant to save model time and
tokens by collecting review context once; it became a judge of the model's
work — stages, schemas, receipts, digest bindings, refusals. The rework keeps
the mechanical guarantees and removes the adjudication.

The external `ocr` CLI (OpenCodeReview; the tested minimum is v1.13.6)
provides the review engine: `ocr review --provider/--model/--effort
low|medium|high --background-file <md> --format json --audience agent --from/--to/--repo/--output`, sessions under `~/.opencodereview/sessions/`
with `ocr session list/show/comments/compare/export`, `ocr review --resume <id>`, and an 8000-byte background-file limit. It is a CLI, so behavior is
identical on opencode, codex, and claude. `ocr llm providers` lists built-in
providers without secrets; custom providers and their models are only in
`~/.opencodereview/config.json`, which the skill never reads.

GitLab draft notes provide the publication flow: a non-interactive `glab api`
block creates drafts; the human edits and publishes in the web UI.

Shared references carry the reply voice: `humanize-patterns.md` (18 KB),
`clarity-rules.md` (1.6 KB), and a new `discussion-replies.md`. They are
materialized through `shared/manifest.json`, so the skill does not depend on
the `humanize` or `eli5` skills being installed.

Two known defects stay on the fix list: `apps/reviewmatic/README.md` claims
an optional `--repo-root` with a managed clone fallback while
`review_worktree.py:474` requires a checkout, and OpenSpec is mentioned
nowhere in `skills/code-review/` or `apps/reviewmatic/src/` — moot for now,
because OpenSpec is out of scope for this change.

## Goals / Non-Goals

**Goals:**

- One central question: does the change solve the task it was made for?
- Identical behavior on opencode, codex, and claude: the review engine is an
  external CLI, not host-specific subagents.
- One question round at the start, then fully autonomous until the report.
- The runbook keeps its current shape, with only the changes listed in D9.
- The human publishes through GitLab draft notes in the web UI.
- Replies read as the user's own, in the discussion's context.
- The runtime is a helper: it assembles context and checks mechanical facts;
  it never judges content.
- No runtime dependency on other skills: the reply and clarity rules are
  bundled.

**Non-Goals:**

- Task assessment: necessity, priority, triage, planning, spec authoring.
- OpenSpec integration — out of scope; may return later.
- Local WIP review — removed with the rename to `mr-review`.
- In-house critics, arbitrator receipts, and the incremental state machine —
  replaced by OCR runs and OCR sessions.
- Autonomous publication of anything.
- Reading `~/.opencodereview/config.json` or any file that holds secrets.

## Decisions

### D1. Fulfillment is the center (confirmed)

`code-review` answers whether the implementation fulfills the agreed task.
The definition of that task comes from upstream — linked GitLab issues, the
MR description, and human answers — and is taken as given. The seeded
`solves-original-problem` question is the fulfillment question and stays
first. If the implementation exposes a gap or contradiction in the task
statement, the review records it as a doubt with the possible readings and
who decides; it does not re-plan or author a specification.

### D2. `ocr` is the only review engine (confirmed)

The OpenCodeReview CLI reviews the diff. It is a declared dependency on the
same level as `glab` and lands in `references/requirements.json` with the
minimum tested version 1.13.6. The in-house critic/receipt/arbitration
machinery and the OCR-as-panel-member path are removed. Depth is chosen by
runs: one run by default, more runs with different
`--provider/--model/--effort`. Findings come only from OCR runs — never from
the manager.

### D3. Manager contract (confirmed)

The manager: collects context; asks the single startup round; authors the
OCR background; starts the OCR run(s); when several runs were selected,
merges duplicates and conflicts with recorded reasons — the arbitration,
surfaced in the runbook; when a previous session exists for the MR, runs
`ocr session compare old new` and feeds the grouping into the runbook;
synthesizes the fulfillment verdict, the SemVer assessment, one architecture
paragraph, and the simplified checks; writes the runbook and the draft-note
block; reports the process to chat and stops.

The manager never: hunts for defects in the diff itself; adds its own
findings — a suspicion becomes a question without severity or buys one more
pointed OCR run; silently drops or downgrades an OCR finding — the reason is
recorded (duplicate, out of scope, contradicts the confirmed task baseline);
publishes anything; substitutes itself for a failed OCR run — it reports the
failure and stops.

### D4. Incrementality is OCR sessions (confirmed)

Every run persists a session. A follow-up review of the same MR is a fresh
run over the current range plus `ocr session compare` against the previous
session: new / persisting / resolved / not-reviewed, matched on path,
category, and the offending snippet. The reviewer always sees current code —
no anchoring on old findings and no ledger reconciliation. `--resume` serves
interrupted runs. The in-house incremental state machine is removed, and the
clean-versus-incremental startup question disappears: compare runs
automatically when a previous session exists. A compressed prior-review
summary — verdict, accepted risks, open questions — still rides in the
background file as context, not as a checklist.

### D5. One startup round, then autonomous (confirmed)

After the read-only collection the manager asks exactly once: the OCR
model(s) and effort (default the profile default; effort default `medium`,
both overridable), and the confirmation of the task baseline — goal and
acceptance criteria from the linked issues and the MR description. There is
no clean-versus-incremental question. Everything afterwards runs without
user interaction until the final chat report.

### D6. Review profiles (confirmed)

- Global `~/.reviewmatic/reviewers.json`; local `./.reviewmatic/reviewers.json`
  found in the current directory, then the git root.
- The local file overlays the global one: a matching alias replaces, new
  aliases add, and the local `default` wins.
- Contents: `default` plus `reviewers[]` with `alias`, `provider`, `model`,
  and `effort`. No secrets.
- The skill never reads `~/.opencodereview/config.json`. Provider names may
  be validated with `ocr llm providers`, which prints built-in providers
  without secrets; custom providers and model names come from the profile.
- Startup: with a profile, its aliases are offered (multi-select, one by
  default); without one, OCR's configured default or a one-off
  provider/model, with an offer to save it to the profile.
- Several selected aliases run as parallel `ocr review` processes, each with
  its own `--output`; the manager merges the results.
- The profile is created explicitly by the user or a setup command; no
  secrets are ever written.

### D7. Background file (confirmed)

The manager authors `background.md`: the task goal, acceptance criteria, the
essence of unresolved discussions, the CI status, and the compressed
prior-review context. The runtime enforces OCR's 8000-byte limit with
disclosed cuts; the full GitLab context stays with the manager for the
runbook.

### D8. Reply voice and thread replies (confirmed)

- A new shared `shared/references/discussion-replies.md` is materialized into
  the skill. It requires: reading the whole thread and the MR context;
  answering the latest relevant point first, then adding only new
  information; writing from the authenticated user's first person and
  factual role; not narrating the user in the third person or attributing
  actions, decisions, or promises they did not make; staying on the
  discussion's subject; no code suggestions; no invented reactions;
  addressing the participant naturally without forcing a pronoun; preserving
  exact tokens.
- `clarity-rules.md` is materialized and applied for plain language.
- `humanize-patterns.md` is materialized in full and bundled, so no other
  skill is required. The fast path reads `discussion-replies.md` and
  `clarity-rules.md`; the full catalog is available for an optional final
  editing pass, not required for every reply.
- Open discussions: all are processed; a substantive reply is drafted where
  one is needed.
- Closed discussions: a reply is drafted only when the problem is still
  relevant on the current head; it is paired with a reopen. Otherwise no
  action.
- Replies are published as draft notes, never directly.

### D9. Runbook (confirmed)

Keep the current format. Changes:

- `Review panel` becomes `OCR runs` (provider, model, effort per run).
- `Arbitration verdicts` appears only when several runs were merged.
- `Local fixes` is removed with the local mode.
- `Manual publication preflight` becomes the draft-note block (D10).
- `Previous findings` is fed by `ocr session compare`.
- A `Task fulfillment` block is added: solves / partially / not, with
  evidence.
- `SemVer impact` stays as is.
- `Project labels` is removed.
- `MR metadata` — the five-field recommendation and the auto-mode proposal
  comment — is removed.
- `Architecture assessment` stays as one manager-written paragraph.
- `Checks` is simplified: pipeline status, failed jobs one line each, what
  the OCR runs covered, and what stayed unverified — no deep per-job trace
  classification.

### D10. Draft notes (confirmed)

The runbook ends with one `sh` block of non-interactive `glab api` calls that
create GitLab draft notes — positioned diff drafts where a position derives
from the finding and the exact base/head, general MR drafts otherwise; thread
replies use `in_reply_to_discussion_id` where GitLab supports it. The block
starts with one head check against the reviewed head and stops on a mismatch.
No publish command exists. The human opens the MR in the GitLab UI, edits the
drafts, and submits the review there. The runbook carries each finding's
essence, severity, and location — not the full bodies.

### D11. Chat report (confirmed)

The final chat report describes the process only: what was collected and what
failed; each OCR run (alias, provider, model, effort, parallel or serial,
duration, exit code, findings count); the merge result when several runs were
used; limitations (background cuts, unavailable CI traces); the runbook path
and the draft block path; the next step. No MR verdict or assessment in chat.

### D12. Rename and scope cut (confirmed)

The skill is renamed `code-review` → `mr-review`; the local WIP mode is
removed. The rename touches the skill directory, `SKILL.source.md`,
`shared/manifest.json`, `shared/skill-relations.json`, the reviewmatic
profile paths, artifact type names, the contract test,
`docs/reference/code-review.md` with its Russian mirror, the skill catalog,
and the host command. The OpenSpec change directory keeps its name
(`spec-code-review`).

### D13. The runtime is a helper, never a judge (confirmed)

The runtime keeps only mechanical guarantees: complete read-only collection,
exact refs, the background-file limit, freshness, redaction, no remote
mutations, profile loading, and draft-note command generation. It does not
validate semantic content, runs no stage machine, and never blocks on prose.
Its command surface is derived from these duties — collect, background,
drafts, revalidate, runtime-info; the exact names are an implementation
detail.

## Risks / Trade-offs

- \[The 8000-byte background starves context] → prioritized compression with
  disclosed cuts; task and acceptance criteria first; the manager keeps the
  full context for the runbook.
- \[`ocr` output drift across versions] → minimum version 1.13.6 in
  `requirements.json`; tolerant parsing with fixtures.
- \[The manager quietly becomes a second reviewer] → D3's never-list;
  findings originate only from OCR runs.
- \[Sessions live per host under `~/.opencodereview`] → compare needs the same
  host; the runbook's compressed context travels without it.
- \[Draft notes need a recent GitLab] → capability check at collection;
  fallback to general drafts, never to direct publishing.
- \[`session compare` heuristics mis-group findings] → the grouping is
  advisory context in the runbook; verdicts stand on the current run.
- \[Bundling the 18 KB humanize catalog grows the archive] → it is a
  reference read only on the optional final pass; the fast path reads the
  compact `discussion-replies.md` and `clarity-rules.md`.
- \[Profile overlay surprises] → local wins by alias and default; the
  effective profile is printed at startup.
- \[The rename misses a coupled surface] → a dedicated task with a grep sweep
  and the contract test updated in the same change.

## Implementation notes

- GitLab draft notes must be verified against the target GitLab version;
  `in_reply_to_discussion_id` is used where supported, otherwise a general
  draft note.
- OCR minimum version: 1.13.6, the tested floor.
- Profile discovery: the current directory, then the git root; the first
  local file overlays the global one.
- The shared references are materialized through `shared/manifest.json`;
  `discussion-replies.md` is new, `humanize-patterns.md` and
  `clarity-rules.md` already exist.
- The runtime's exact command names are chosen during implementation.
