# Design

> Capture after the OCR-engine round, 2026-11-09. Still not final. Decisions
> are marked (confirmed); the manager boundary in D3 and two runbook items in
> D8 are (proposed) pending the owner's confirmation.

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

The engine decision reverses the runtime's drift. The owner's original goal
was a helper that saves model time and tokens by collecting review context
once; the runtime instead became a judge of the model's work — stages,
schemas, receipts, digest bindings, refusals. The rework keeps only the
mechanical guarantees.

The external `ocr` CLI (OpenCodeReview; v1.13.6 is installed here) provides
the review engine: `ocr review --provider/--model/--effort
low|medium|high --background-file <md> --format json --audience agent
--from/--to/--repo/--output`, sessions persisted under
`~/.opencodereview/sessions/` with `ocr session
list/show/comments/compare/export`, `ocr review --resume <id>`, and an
8000-byte background-file limit. GitLab draft notes provide the publication
flow: commands create drafts, the human edits and publishes in the web UI.

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
- The runbook keeps its current shape, with only the changes listed in D8.
- The human publishes through GitLab draft notes in the web UI.
- The runtime is a helper: it assembles context and checks mechanical facts;
  it never judges content.

**Non-Goals:**

- Task assessment: necessity, priority, triage, planning, spec authoring.
- OpenSpec integration — out of scope for this change; may return later.
- Local WIP review — removed together with the rename to `mr-review`.
- In-house critics, arbitrator receipts, and the incremental state machine —
  replaced by OCR runs and OCR sessions.
- Autonomous publication of anything.

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
same level as `glab` and lands in `references/requirements.json`. The
in-house critic/receipt/arbitration machinery and the OCR-as-panel-member
path are removed. Depth is chosen by runs: one run by default, more runs
with different `--provider/--model/--effort`. Findings come only from OCR
runs — never from the manager.

### D3. The main session is the manager (proposed boundary)

The manager: collects context (fast, read-only); asks the single startup
round; authors the OCR background; starts the OCR run(s); when several runs
were selected, merges duplicates and conflicts with recorded reasons — the
arbitration, surfaced in the runbook; when a previous session exists for the
MR, runs `ocr session compare old new` and feeds the grouping into the
runbook; synthesizes the fulfillment verdict, the SemVer assessment, a short
architecture paragraph, and the checks and limitations; writes the runbook
and the draft-note block; reports to chat and stops.

The manager never: hunts for defects in the diff itself; adds its own code
findings — a suspicion goes to questions or limitations without severity, or
buys one more pointed OCR run; silently drops or downgrades an OCR finding —
the reason is recorded (duplicate, out of scope, contradicts the confirmed
task baseline); publishes anything; substitutes itself for a failed OCR run
— it reports the failure and stops.

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

### D5. One question round, then autonomous (confirmed)

After the read-only collection the manager asks exactly once: the OCR
model and effort (default: the configured one; optionally a second run) and
the confirmation of the task baseline — goal and acceptance criteria from
the linked issues and the MR description. Everything afterwards runs without
user interaction until the final chat report.

### D6. The background file (confirmed)

The manager authors `background.md` for the OCR run: the task goal,
acceptance criteria, the essence of unresolved discussions, the CI status,
and the compressed prior-review context. The runtime writes the file and
enforces OCR's 8000-byte limit with disclosed cuts; the full GitLab context
stays with the manager for the runbook.

### D7. Publication through draft notes (confirmed)

The runbook ends with one `sh` block of non-interactive `glab api` calls
that create GitLab draft notes — positioned diff drafts where a position
derives from the finding and the exact base/head, general MR drafts
otherwise. No publish command exists. The human opens the MR in the GitLab
UI, edits the drafts, and submits the review there. The runbook carries each
finding's essence, severity, and location — not the full publication bodies,
which the human checks in the UI.

### D8. Runbook: keep the shape, listed changes only (confirmed; two items proposed)

Keep the current runbook format. Changes:

- `Review panel` becomes `OCR runs` (provider, model, effort per run).
- `Arbitration verdicts` appears only when several runs were merged.
- `Local fixes` is removed with the local mode.
- `Manual publication preflight` becomes the draft-note block (D7).
- `Previous findings` is fed by `ocr session compare`.
- A `Task fulfillment` block is added: solves / partially / not, with
  evidence.
- `SemVer impact` stays as is.
- `Project labels` is removed.
- `MR metadata` — the five-field recommendation and the auto-mode proposal
  comment — is removed.
- (proposed) `Architecture assessment` stays as one manager-written
  paragraph.
- (proposed) `Checks` stays simplified: pipeline status, failed jobs one
  line each, what the OCR runs covered, what stayed unverified — deep
  per-job trace classification is dropped.

### D9. Rename and scope cut (confirmed)

The skill is renamed `code-review` → `mr-review`; the local WIP mode is
removed. The rename touches the skill directory, `SKILL.source.md`,
`shared/manifest.json`, `shared/skill-relations.json`, the reviewmatic
profile and XDG paths, artifact type names, the contract test,
`docs/reference/code-review.md` with its Russian mirror, the skill catalog,
and the host command. The OpenSpec change directory keeps its name
(`spec-code-review`).

### D10. The runtime is a helper, never a judge (confirmed)

The runtime keeps only mechanical guarantees: complete read-only collection,
exact refs, the background-file limit, freshness, redaction, no remote
mutations, and draft-note command generation. It does not validate semantic
content, runs no stage machine, and never blocks on prose. Its command
surface is derived from these duties — collect, background, drafts,
revalidate, runtime-info; the exact names are an implementation detail.

## Risks / Trade-offs

- [The 8000-byte background starves context] → prioritized compression with
  disclosed cuts; task and acceptance criteria first; the manager keeps the
  full context for the runbook.
- [`ocr` output drift across versions] → pin the version in
  `references/requirements.json` like the runtime pin; tolerant parsing with
  fixtures.
- [The manager quietly becomes a second reviewer] → D3's never-list;
  findings originate only from OCR runs.
- [Sessions live per host under `~/.opencodereview`] → compare needs the
  same host; the runbook's compressed context travels without it.
- [Draft notes need a recent GitLab] → capability check at collection;
  fallback to general drafts, never to direct publishing.
- [`session compare` heuristics mis-group findings] → the grouping is
  advisory context in the runbook; verdicts stand on the current run.
- [The rename misses a coupled surface] → a dedicated task with a grep sweep
  and the contract test updated in the same change.

## Open Questions

1. The manager boundary in D3 — confirm the never-list, especially that a
   suspicion buys one more OCR run instead of a manager finding.
2. The two proposed runbook items in D8: the architecture paragraph and the
   simplified checks.
3. Model selection detail: default to `ocr`'s configured provider/model and
   offer a manual override plus an optional second run — or list candidates?
   `ocr config` is interactive and has no list command.
4. OCR version pinning policy: an exact version in requirements.json versus
   a minimum.
5. Whether to expose `--effort` in the startup round or fix it (default
   medium).
