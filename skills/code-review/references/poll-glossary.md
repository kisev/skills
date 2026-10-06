# Panel poll glossary

The runtime renders the poll text verbatim, keyed to the review locale; this
glossary fixes the meaning of every term the poll and the engines note use.

- **Poll** — the single question the review asks at its start: the critic
  composition and the engine of every critic, plus the arbitrator. It is asked
  once per review; a recorded answer is never re-asked.
- **Critic** — one independent reviewer over the collected context and the
  exact snapshots. Each selected critic returns one receipt with findings.
- **Engine** — how one critic runs: `"model"` or `"ocr"`. The engine is a
  per-critic choice, not a panel-wide one.
- **Model engine** (`"engine": "model"`) — the critic runs as an independent
  model subagent with the session's agent, provider, and model.
- **OCR engine** (`"engine": "ocr"`) — the critic runs mechanically as the
  OpenCodeReview CLI: the runtime renders the background, invokes the CLI,
  and maps its comments into a receipt. An incremental review scopes the OCR
  engine to the delta from the previous reviewed head and includes the
  previously reported findings the delta touches in its background; only the
  size note (the background file exceeds the CLI's limit) excludes the engine.
- **Arbitrator** — the separate participant that merges every critic finding
  into one verdict; never one of the critics.
- **Panel** — the recorded answer: the critics with their engines plus the
  arbitrator. It is fixed once any critic receipt is bound.
- **Selection template** — the JSON file the stop materializes; the answer is
  recorded by filling it and running the printed command.
- **Mode note** — the resolved review mode the poll names, with the exclusion
  reason when the OCR engine cannot be offered.
