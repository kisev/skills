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
  subagent on the current session's agent, provider, and model. A subagent on
  the current model is a valid role without any installed profile.
- **OCR engine** (`"engine": "ocr"`) — the critic runs mechanically as the
  OpenCodeReview CLI: the runtime renders the compact background, invokes the
  CLI, and maps its comments into a receipt. An incremental review scopes the
  OCR engine to the delta from the previous reviewed head and includes the
  previously reported findings the delta touches in its background; only the
  size note (even the compacted background exceeds the CLI's limit) excludes
  the engine, and that note names the compacted size and the cut sections.
- **Compact background** — the one background render the poll measures and the
  OCR critic executes: thread registry entries and open questions stay
  verbatim on single lines, one uniform relevance hoists into a single line,
  and byte caps clamp goal, acceptance criteria, claims, constraints, prior
  decisions, and the task narrative; the advisory history is a single-line
  JSON. Nothing unasked is truncated: the note reports the compacted byte
  size and the cut sections.
- **Independence** — the depth unit of the panel: two critics are independent
  reviewers only when they differ in model, engine, or installed profile; two
  critics on the same single model are never offered as more depth.
- **Arbitrator** — the separate participant that merges every critic finding
  into one verdict; never one of the critics. Its status is explicit: a
  subagent on the same model as the session, or a selected specialist profile.
- **Installed profile** — a specialist agent installed in this host, named by
  the poll's composition variants only when the agent verified those profiles
  first (`agentomatic agent list` / the profile manifest); a multi-critic
  composition is offered only when installed profile critics differ in model
  or engine, and two critics on the same single model are never offered.
- **Panel** — the recorded answer: the critics with their engines plus the
  arbitrator. It is fixed once any critic receipt is bound.
- **Selection template** — the JSON file the stop materializes; the answer is
  recorded by filling it and running the printed command.
- **Mode note** — the resolved review mode the poll names, with the exclusion
  reason when the OCR engine cannot be offered: the compacted size and the
  cut sections.
