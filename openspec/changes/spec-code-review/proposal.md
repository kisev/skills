# Proposal

## Why

`code-review` is a core, frequently used skill (foundation decision D8). The owner diagnosed it as heavy, complex, and slow: the text corpus and the `reviewmatic` runtime grew around a full code-audit product — panel poll, multi-critic arbitration, an in-house OCR-critic bridge, SemVer and labels, suggestions and patches, repair paths — while the actual job is simpler and more human-centered. The runtime was meant as a helper that saves model time and tokens by collecting review context once; it became a judge of the model's work instead.

The owner's working model: the human stays the principal participant; the LLM removes the routine so the human can focus on design, authorial intent, and principles. The task definition is produced upstream — by a person, another skill, or a linked issue — and the review consumes it as an agreed boundary.

## What Changes

Reframe the skill around one central question: **does this change solve the task it was made for?** The task definition is an input, taken as given; "take on faith" applies to the definition, not to the fulfillment.

- **The reviewer is the external `ocr` CLI** (OpenCodeReview) — the only engine, a declared dependency on the level of `glab`. The in-house critic/receipt/arbitration machinery and the incremental state machine are removed. Depth is chosen by runs: one by default, more with different provider/model/effort.
- **The main session is a manager**: it collects context, asks one startup round (OCR model/effort, optional second run, confirmation of the task baseline), then runs autonomously; merges runs when several were selected; synthesizes the fulfillment verdict, SemVer, a short architecture paragraph, and the checks; writes the runbook and reports. It never hunts for defects itself.
- **Incrementality is OCR sessions**: a fresh run over the current range plus `ocr session compare` against the previous session (new / persisting / resolved / not-reviewed); `--resume` for interrupted runs. No ledger reconciliation, no anchoring on old findings.
- **Publication goes through GitLab draft notes**: one non-interactive `sh` block creates drafts (positioned where a position derives, general otherwise); the human edits and publishes in the GitLab UI. The runbook carries each finding's essence, severity, and location — not the full publication bodies.
- **The runbook keeps its current format** with listed changes: `Review panel` becomes `OCR runs`, `Arbitration verdicts` appears only for merged runs, `Local fixes` is removed, the publication section becomes the draft block, `Previous findings` is fed by session compare, a `Task fulfillment` block is added, `SemVer impact` stays, `Project labels` and `MR metadata` are removed.
- **The skill is renamed `code-review` → `mr-review`** and the local WIP mode is removed. OpenSpec integration is out of scope for this change.
- **`reviewmatic` shrinks to a helper runtime** (collect, background, drafts, revalidate): mechanical guarantees only — complete read-only collection, exact refs, the 8000-byte background limit, freshness, redaction, no remote mutations — with no stage machine and no semantic validation.

## Capabilities

### New Capabilities

None yet — the capability spec is drafted after the open questions in `design.md` are decided.

### Modified Capabilities

None.

## Impact

`skills/code-review` (renamed `mr-review`), `apps/reviewmatic` (major reduction, together with `spec-reviewmatic`), `shared/manifest.json` and `shared/skill-relations.json`, `references/requirements.json` gains `ocr`, `docs/reference/code-review.md` with its Russian mirror and the skill catalog, the reviewmatic profile and XDG paths, the contract test, and the host command rename.
