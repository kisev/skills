---
audience: user
review: {"components": ["reviewmatic"], "sources": ["apps/reviewmatic/src/reviewmatic/ocr_critic.py", "apps/reviewmatic/src/reviewmatic/draft.py", "apps/reviewmatic/src/reviewmatic/local_review.py", "apps/reviewmatic/src/reviewmatic/cli.py", "apps/reviewmatic/tests/test_ocr_critic.py"], "contracts": ["specs/capabilities/skills/code-review.md", "skills/code-review/references/workflow.md"]}
---

# Run the OCR Critic in a Review Panel

[Русский](../ru/how-to/ocr-critic.md)

The OpenCodeReview CLI (`ocr`) can join a review panel as a mechanical critic
alongside model critics, or as the only critic. It reviews the same recorded
change, reports findings into one critic receipt, and the arbitrator verdicts
its findings exactly like any model critic's. OCR never answers
critic-assigned questions.

## Select the Composition

Record the panel as usual with `reviewmatic record-participants` and mark the
OCR critic with `engine`:

```json
{
  "critics": [
    {"name": "ocr-critic", "engine": "ocr"},
    {"name": "critic-general", "profile": "critic-general"}
  ],
  "arbitrator": {"name": "arb-main"}
}
```

Pin the LLM used by the run with the command flags; without them the OCR CLI
uses its own provider configuration:

```shell
reviewmatic record-participants --draft <draft> --input participants.json \
  --ocr-provider openai --ocr-model claude-opus-4-6
```

A recorded selection without `engine: "ocr"` critics rejects the flags with an
addressed error, so a stray configuration never silently does nothing.

## Run the Critic

After the context package is recorded, the runtime returns one ready task per
critic. A model critic's task carries a receipt template and an
`import_command`; an OCR critic's task carries the exact `run_command`:

```shell
reviewmatic record-ocr-critic --draft <draft> --participant ocr-critic
```

For a local review the same command targets the snapshot:

```shell
reviewmatic record-ocr-critic --bundle <snapshot> --participant ocr-critic
```

One invocation performs the whole mechanical critic pass:

1. Renders the recorded context package as a Markdown background file under
   the artifact root.
2. Invokes `ocr review --format json --audience agent` with a 300-second
   timeout — over the recorded base..head range in the managed review worktree
   for a remote MR, or in workspace mode (staged, unstaged, and untracked
   changes) for a local review without a ref.
3. Maps every OCR comment into one receipt: `severity`, `path`, and
   `start_line`..`end_line` land in the finding fields, `category` and
   `suggestion_code` feed the fix and risk text, and the receipt keeps the
   OCR run identity plus an `engine: "ocr"` marker with provider, model,
   terminal state, and comment count.
4. Imports the receipt verbatim with the standard `record-critic` path and
   binds it to the participant, exactly like a model critic's receipt.

If the OCR CLI is missing, fails, or returns a run without a persistent
session identity, the command fails with a concrete error and the draft stays
unchanged; rerun the command after fixing the OCR setup.

## Arbitration and Boundaries

The arbitrator receives OCR receipts together with model receipts and gives
every OCR finding a verdict. Because OCR produces findings only, a panel
without model critics must resolve every critic-assigned question through
arbitration `question_verifications`. Incremental reviews scope the OCR critic
to the `from_head..head` delta: the receipt binds the incremental delta digest,
and `target_finding_ids` names exactly the previously reported findings
rendered into the background — those whose previous publication position or
patch intersects the changed paths. Local OCR critics stay full-scope: the
local receipt schema has no scope fields, so incremental local panels run
model critics for the delta.
