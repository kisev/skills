# Review panel

For `normal` and `incremental` reviews the review runs as a panel and
you orchestrate it; you never add a full review pass of your own. The panel
composition is the depth control: a deeper review is requested by adding more
independent critics, and there is no separate depth mode. First record
the panel with `reviewmatic record-participants --draft <draft-path> --input <participants.json>`: the critic count and composition, then the arbitrator.
Each role is either an installed specialist profile (`critic-*` agents) or one
independent subagent on the current session's agent, provider, and model; a role
may also be the mechanical `ocr` engine. Ask for
the panel selection in one poll at the start of every panel review, in the
same single question round as any missing task context: the critic
composition, the engine of every critic, and the arbitrator. Attach your
recommendation to the poll; the choice is the user's. Before composing the
options, check the installed critic profiles (`agentomatic agent list`):
multi-critic options are proposed only when installed profile critics with
distinct models or engines exist, and a composition of two critics on the
same single model is never proposed — it is not an independent check. An
explicit user skip records exactly that answer — one subagent on the current
session's model as the critic and one arbitrator subagent on the same model —
but an unanswered poll is never filled silently: wait for the answer. Never
substitute a configuration silently: the recorded profile, provider, and model
names appear in the runbook, and the arbitrator receipt must name the selected
arbitrator.
After the package is recorded, the runtime returns one ready critic task per
selected participant with the exact receipt template and the exact
`record-critic --participant <name>` import command. Launch every selected
critic in parallel, in native background mode when supported. Each critic
performs one complete independent review from the same recorded package and
the exact snapshots: findings plus answers to its assigned questions. Pass the
materialized `references/simplification-criteria.md` path into every critic
task and into the arbitrator task alongside the package and snapshot paths, so
complexity candidates follow the shared tags, evidence, usage-check, and safety
floor. Critics report complexity as normal findings with every required field,
and the arbitrator verdicts each complexity candidate without dropping a
refuted one. Critics
never see each other's output, never recollect GitLab, never rebuild the
prepared file map, and may read related code inside the review worktree.
Every finding must trace its symptom to the changed lines: follow the failing
path from the observed symptom through concrete code to the diff
(symptom-path tracing), and a claim about unreachable or dead code requires
proving unreachability by checking every caller from a real entrypoint
(reachability from entrypoint). Import each receipt verbatim with its exact `--participant` name; the runtime
binds the receipt identity to the participant and rejects a re-used identity.

### OCR critic

A panel critic may also be the OpenCodeReview CLI instead of a model subagent.
Record it with `"engine": "ocr"` on the critic entry in the
`record-participants` input; pass `--ocr-provider` and `--ocr-model` to pin the
LLM for the run (without them the OCR CLI uses its own provider configuration).
A panel can be mixed or purely OCR. After the package is recorded, the runtime
returns one ready task per OCR critic with the exact
`reviewmatic record-ocr-critic` command; run it like any returned action. In
the run path above there is no such stop: the runtime executes OCR critics
itself, without an authoring stop. reviewmatic renders the recorded package as
a Markdown background file, invokes
`ocr review --format json --audience agent` over the exact reviewed range (the
base..head range in the review worktree for a full remote-MR review; the
`from_head..head` delta for an incremental review; workspace mode for a
local review without a ref), maps every comment into one receipt carrying the
OCR run identity, and binds it to the participant exactly like a model critic
receipt. OCR produces findings only: it never answers critic-assigned
questions, so when no model critic is selected the arbitrator resolves every
assigned question through `question_verifications`. In incremental reviews the
receipt binds the incremental delta digest and `target_finding_ids` names
exactly the previously reported findings rendered into its background (the
coverage boundary lives in `references/incremental-review.md`); the bilingual
runbook lives at
`docs/how-to/ocr-critic.md` with its Russian mirror under `docs/ru/how-to/`.
When the last critic receipt is imported, the response returns the ready
arbitrator task with a complete arbitration input: the same package binding,
every critic receipt verbatim, and the reported question contradictions.
Launch the selected arbitrator as a separate subagent. It confirms or refutes
every critic finding with a concrete reason, resolves every contradiction and
`not_verified` answer through targeted evidence checks against the exact
snapshots, merges duplicates without losing authors or opinion differences,
and records the consolidated decisions — including thread outcomes, labels,
CI classification, SemVer, and the metadata assessment — in one
`code-review/arbitration/v1` receipt. It must not start a new defect search
from scratch; majority agreement or a model's name never replaces a reason.
Import the receipt verbatim with `reviewmatic record-arbitration --draft <draft-path> --input <receipt>`; the runtime rejects a receipt that leaves any
critic finding or contradiction without a verdict and never rewrites
arbitrator text. In panel mode `record-input` accepts only `run_id`,
`session_id`, and `low_risk` from you: every other semantic decision belongs
to the arbitration receipt.

### Verdict ladder

The arbitration receipt must select exactly one merge verdict — `decline`,
`push_back`, `merge_then_fix`, or `merge` — in the required `merge_verdict`
field with an evidence-based `merge_verdict_rationale`; the runtime rejects a
receipt without it and renders the verdict in the runbook, summary, and chat.
The tie-breaker is whose knowledge survives the remainder: when the missing
knowledge lives with the author — product intent or domain facts only they
hold — choose `push_back`; when it lives with this review — the fix is local
and the evidence is in the exact snapshots — choose `merge_then_fix`. An
unresolved product question may carry a conditional verdict recorded in the
rationale, for example "PUSH-BACK if the feature is needed, DECLINE if not".
A `decline` still salvages the ache: the MR closes, but the pain it attempted
to solve is recorded as a recommended issue so the problem outlives the
rejected change.

### Findings discipline

The arbitrator filters; the critics never see the filter. A critic finding
enters the runbook findings and the action list only when it moves the merge
verdict or the readiness verdict, or joins the action list as a validated fix,
a thread decision, or a recommended issue. Every other candidate stays in the
ledger as a refuted or duplicate entry with its concrete reason — a
disagreement never hides a finding, but it also never dilutes the action list.
Each critic reports every finding it can support, without ranking it against
the arbiter's gate.
The recording response returns the recorded package
path and digest, the question context versions, the exact evidence/context/
inspection paths, the receipt template, and the exact import command. Pass
those exact paths — never manually transcribed evidence or duplicate
collection requests. The runtime rejects stale answers that bind another
package version instead of rebinding them. Join before validation. Report
collection, package recording, critic waiting, arbitration, fix checks, and
finalization separately; do not promise a numerical SLA or reduce review
depth. Follow `references/context-package.md` for the package content, the
answer verdicts, and the resume/refresh lifecycle, and
`references/review-state-machine.md` for the full panel contract.
