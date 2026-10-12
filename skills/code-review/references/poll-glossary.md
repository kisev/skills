# Panel poll glossary

This glossary fixes the meaning of every term the poll and the engines note
use; the runtime renders the poll text verbatim, keyed to the review locale.

- **Poll** — the single question the review asks at its start: the critic
  composition and the engine of every critic, plus the arbitrator. It is asked
  once per review; a recorded answer is never re-asked.
- **Critic** — one independent reviewer over the collected context and the
  exact snapshots. Each selected critic returns one receipt with findings.
- **Engine** — how one critic runs: `"model"` or `"ocr"`. The engine is a
  per-critic choice, not a panel-wide one.
- **Model engine** (`"engine": "model"`) — the critic runs as an independent
  subagent on the current session's agent, provider, and model; a valid role
  without any installed agent.
- **OCR engine** (`"engine": "ocr"`) — the critic runs mechanically as the
  OpenCodeReview CLI: the runtime renders the compact background, invokes the
  CLI, and maps its comments into a receipt. An incremental review scopes it
  to the delta from the previous head including the touched previous
  findings; only the size note (compacted size, cut sections) excludes it.
- **Compact background** — the one render the poll measures and the OCR
  critic executes: thread registry entries and open questions verbatim, one
  uniform relevance hoisted to a single line, byte caps over goal, acceptance
  criteria, claims, constraints, prior decisions, and the task narrative; the
  advisory history is a single-line JSON. Nothing unasked is truncated: the
  note reports the byte size and cut sections.
- **Independence** — the depth unit of the panel: two critics are independent
  reviewers only when they differ in model, engine, or installed definition;
  two critics on the same single model are never offered as more depth.
- **Arbitrator** — the separate participant that merges every critic finding
  into one verdict; never one of the critics. Its status is explicit: a
  subagent on the same model as the session, or a selected specialist agent.
- **Composition question** — the host's native interactive question tool that
  collects the user's choice right after the poll is presented verbatim. Its
  minimum option set: the recommended composition, a single model subagent, a
  subagent plus an OCR critic, and a custom composition whose details are
  requested after selection; the recommendation is attached to its own option
  and the choice is the user's.
- **Installed agent** — a specialist agent the host's user configured, named by
  the poll's composition variants only when the agent verified the pool first
  (`agents/*.md` in the harness-global and project config directories, and the `agent` key of the global and project `opencode.json`; never the bundled agent
  assets of installed packages or plugins, anything under `node_modules/` —
  installation sources deployed only through `configure agent`); a multi-critic
  composition is offered only when installed agents differ in model or
  engine, and two critics on the same single model are never offered. An
  agent defined without a model runs on the primary session's model; a
  source that cannot be read leaves the installed pool unknown, not empty,
  and a pool that reads as empty recommends the default composition — one
  model-subagent critic and one arbitrator subagent.
- **Panel** — the recorded answer: the critics with their engines plus the
  arbitrator. It is fixed once any critic receipt is bound.
- **Selection template** — the JSON file the stop materializes; the agent
  fills the selection template from the user's answer to the composition
  question and runs the printed command.
- **Mode note** — the resolved mode the poll names, with the exclusion
  reason when the OCR engine is excluded.
