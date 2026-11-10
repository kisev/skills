# Proposal

## Why

`code-review` is a core, frequently used skill (foundation decision D8). The owner diagnosed it as heavy, complex, and slow: the text corpus and the `reviewmatic` runtime grew around a full code-audit product — panel poll, multi-critic arbitration, an in-house OCR-critic bridge, SemVer and labels, suggestions and patches, repair paths — while the actual job is simpler and more human-centered. The runtime was meant as a helper that saves model time and tokens by collecting review context once; it became a judge of the model's work instead.

The owner's working model: the human stays the principal participant; the LLM removes the routine so the human can focus on design, authorial intent, and principles. The task definition is produced upstream — by a person, another skill, or a linked issue — and the review consumes it as an agreed boundary.

## What Changes

Reframe the skill around one central question: **does this change solve the task it was made for?** The task definition is an input, taken as given; "take on faith" applies to the definition, not to the fulfillment.

- **The reviewer is the external `ocr` CLI** (OpenCodeReview), the only engine, a declared dependency on the level of `glab` with the minimum tested version 1.13.6. The in-house critic/receipt/arbitration machinery and the incremental state machine are removed. Depth is chosen by runs: one by default, more with different provider/model/effort.
- **The main session is a manager**: it collects context, asks one startup round (OCR model/effort and confirmation of the task baseline), then runs autonomously; merges runs when several were selected; synthesizes the fulfillment verdict, SemVer, one architecture paragraph, and simplified checks; writes the runbook and reports. It never hunts for defects itself.
- **Models come from a review profile**: `~/.reviewmatic/reviewers.json` globally and `./.reviewmatic/reviewers.json` locally, with the local file overlaying the global one. The profile holds aliases, provider, model, and effort — no secrets. The skill never reads `~/.opencodereview/config.json`. Several selected aliases run as parallel OCR processes.
- **Incrementality is OCR sessions**: a fresh run over the current range plus `ocr session compare` against the previous session (new / persisting / resolved / not-reviewed); `--resume` for interrupted runs. No ledger reconciliation, no anchoring on old findings.
- **Publication goes through GitLab draft notes**: one non-interactive `sh` block creates drafts (positioned where a position derives, general otherwise), starting with one head check; the human edits and publishes in the GitLab UI. The runbook carries each finding's essence, severity, and location — not the full bodies.
- **Thread replies are substantive and in the user's voice**: a new shared `discussion-replies.md` plus `clarity-rules.md` and the bundled `humanize-patterns.md` define first-person replies that read the whole discussion, answer the latest relevant point, and invent no actions or reactions. Open threads are all processed; closed threads get a reply and a reopen only when the problem is still relevant.
- **The chat report describes the process only**: collection, OCR runs, merge, limitations, runbook path, next step — no MR verdict.
- **The runbook keeps its current format** with listed changes: `Review panel` becomes `OCR runs`, `Arbitration verdicts` appears only for merged runs, `Local fixes` is removed, the publication section becomes the draft block, `Previous findings` is fed by session compare, a `Task fulfillment` block is added, `SemVer impact` stays, `Project labels` and `MR metadata` are removed, the architecture paragraph stays, and `Checks` is simplified.
- **The skill is renamed `code-review` → `mr-review`**, the local WIP mode is removed, and OpenSpec integration is out of scope for this change.
- **`reviewmatic` shrinks to a helper runtime**: mechanical guarantees only — complete read-only collection, exact refs, the 8000-byte background limit, freshness, redaction, profile loading, no remote mutations, draft-note command generation — with no stage machine and no semantic validation.

## Capabilities

### New Capabilities

- `mr-review` — the exhaustive merge-request review contract: task boundary, OCR engine, manager, profiles, runbook, draft notes, and replies.

### Modified Capabilities

None.

## Impact

`skills/code-review` (renamed `mr-review`), `apps/reviewmatic` (major reduction, together with `spec-reviewmatic`), `shared/manifest.json` (the new `discussion-replies.md` and the `humanize-patterns.md` / `clarity-rules.md` destinations), `shared/skill-relations.json`, `references/requirements.json` gains `ocr`, `docs/reference/code-review.md` with its Russian mirror and the skill catalog, the reviewmatic profile paths (`~/.reviewmatic`, `./.reviewmatic`), the contract test, and the host command rename.
