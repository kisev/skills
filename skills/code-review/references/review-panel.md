# Review panel

For `normal` and `incremental` reviews the review runs as a panel and
you orchestrate it; you never add a full review pass of your own. The panel composition is the depth control; there is no separate depth mode. First record the
panel with `reviewmatic record-participants --draft <draft-path> --input <participants.json>`: the critic count and composition, then the arbitrator.
Each role is either an installed specialist agent or an independent subagent
on the current session's agent, provider, and model; a role may also be the
mechanical `ocr` engine. Ask for the panel selection in one poll at the start
of every panel review — the critic composition, the engine of every critic,
and the arbitrator — in the same single question round as missing task
context. Attach your recommendation; the choice is the user's. Present the
poll exactly as printed — every line word for word, as one unchanged block,
never restyled into a blockquote, a summary, or new wording; on the run path
the fenced `poll_block` the stop prints is that block, copied fences and all.
Then collect the user's choice with the host's native interactive question
tool: offer at least the recommended composition, a single model subagent, a
subagent plus an OCR critic, and a custom composition that asks for its
details after selection, with the recommendation attached to its own option;
fill the selection template from that answer yourself and run the printed
command yourself — the user never writes JSON. If the interactive
question cannot reach the user, ask the same composition question in plain
text. Before
composing the options, ground the pool in the agents the host's user
configured — the host's agent inventory
(`agents/*.md` in the harness-global and project config directories, and the `agent` key of the global and project `opencode.json`; never the bundled agent assets of installed packages or plugins, anything under `node_modules/`: installation sources deployed only through `configure agent`): options are proposed only
when they exist, multi-critic options only when candidate agents carry
distinct models or engines, and two critics on the same single model are
never proposed — that is not an independent check. An agent defined without a
model runs on the primary session's model; a source that cannot be read
leaves the pool unknown, never empty, and a pool that reads as empty
recommends the same default composition. An explicit skip records exactly the
default — one subagent critic and one arbitrator subagent, both on the
session model — while an unanswered poll is never filled silently. Never
substitute a configuration silently: the recorded profile, provider, and
model names appear in the runbook, and the arbitrator receipt must name the
selected arbitrator.
After the package is recorded, the runtime returns one ready critic task per
selected participant with the exact receipt template, the printed receipt
contract, and the exact
`record-critic --participant <name>` import command. The printed contract is
the complete receipt dictionary: the field dictionary of every finding (`id`,
`severity`, `summary`, `risk`, `evidence[]`, `consequence`,
`relation_to_change`, `minimum_fix`), the field dictionary of every
question answer (`question_id`, `verdict` `confirmed|refuted|not_verified`,
`evidence` or `reason`, and the question's own `context_digest` from the
recorded package), the assigned question ids, and the semantics of that
digest — it names the package version the answer was produced against, never
the evidence digest. Treat the printed contract as complete: never open a
schema or a reference to learn a receipt field, and never copy a digest from
anywhere but the recorded package. Launch every critic in
parallel, in native background mode when supported. Each critic performs one
complete independent review from the same recorded package and exact
snapshots: findings plus answers to its assigned questions, and the
validation question assigned from the context-package contract (does the
change solve the problem it was made for? — the arbitrator weighs those
answers). Every model critic answers every question the package assigns to
critics; one critic's answer never covers another critic's assignment. Pass the
materialized `references/simplification-criteria.md` path into every critic task and into the arbitrator task; critics report complexity as normal findings with every required field,
and the arbitrator verdicts each complexity candidate without dropping a refuted one. Critics never see each other's output, never
recollect GitLab, never rebuild the file map, and may read related code in
the review worktree. Every finding traces its symptom to the changed lines
through concrete code (symptom-path tracing), and an unreachable or dead-code
claim requires proving unreachability from a real entrypoint. Import receipts
verbatim with the exact `--participant` name; the runtime rejects a re-used
identity.

### OCR critic

A panel critic may also be the OpenCodeReview CLI instead of a model
subagent: record it with `"engine": "ocr"` on the critic entry, and pass
`--ocr-provider`/`--ocr-model` to pin the LLM for the run (without them the
CLI uses its own configuration). A panel can be mixed or purely OCR; after
the package is recorded the runtime returns one ready task per OCR critic
with the exact `reviewmatic record-ocr-critic` command, while the run path
executes OCR critics mechanically with no special stop. OCR produces
findings only and never answers critic-assigned questions, so a panel without
a model critic has the arbitrator resolve every assigned question through
`question_verifications`. In incremental reviews the receipt binds the delta
digest and `target_finding_ids` names exactly the previously reported
findings rendered into its background (coverage:
`references/incremental-review.md`); the bilingual runbook is
`docs/how-to/ocr-critic.md` with its Russian mirror.
When the last critic receipt is imported, the response returns the ready
arbitrator task with a complete arbitration input: the same package binding,
every critic receipt verbatim, and the reported question contradictions.
Launch the selected arbitrator as a separate subagent. It confirms or refutes
every critic finding with a concrete reason, resolves every contradiction and
`not_verified` answer through targeted evidence checks, merges duplicates
without losing authors or opinion differences, and records the consolidated
decisions — thread outcomes, labels, CI classification, SemVer, the
validation question, and the metadata assessment — in one
`code-review/arbitration/v1` receipt; it never starts a new defect search
from scratch, and majority agreement never replaces a reason.
Import the receipt verbatim with `reviewmatic record-arbitration --draft <draft-path> --input <receipt>`; the runtime rejects a receipt that leaves any
critic finding or contradiction without a verdict and never rewrites
arbitrator text. In panel mode `record-input` accepts only `run_id`,
`session_id`, and `low_risk` from you: every other semantic decision belongs
to the arbitration receipt.

### Verdict ladder

The arbitration receipt selects exactly one merge verdict — `decline`,
`push_back`, `merge_then_fix`, or `merge` — in the required `merge_verdict`
field with an evidence-based rationale; the runtime refuses a receipt without
it and renders the verdict in runbook, summary, and chat. The tie-breaker is
whose knowledge survives the remainder: author-held intent chooses
`push_back`; locally fixable with evidence in the snapshots choose
`merge_then_fix`. An unresolved product question may carry a conditional
verdict in the rationale. A `decline` salvages the ache as a recommended
issue.

### Findings discipline

The arbitrator filters; the critics never see the filter. A finding enters
the runbook and the action list only when it moves the merge or readiness
verdict, or joins the action list as a validated fix, thread decision, or
recommended issue; every other candidate stays a refuted or duplicate ledger
entry, and each critic reports everything it can support. A claim that
behavior works now, for the first time, or since this bump is a novelty
claim: when the change bumps a dependency, the critic verifies the claim
against the predecessor version - the previously pinned revision - before
reporting it, and when the predecessor is unreachable the residual
uncertainty is recorded at low severity with the unreachable predecessor
named; an unverified novelty claim is never a blocking finding (two false
blockers of exactly this shape reached a live MR review). The recording
response returns the package path and digest, question context versions,
exact snapshot paths, receipt template, and import command — pass those exact
paths, never rebind answers bound to another package version, join before
validation, and report every stage separately. Follow
`references/context-package.md` for the package content, answer verdicts, and
the resume/refresh lifecycle, and `references/review-state-machine.md` for
the full panel contract.
