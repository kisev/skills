# Run path: the primary remote-MR review

Drive a remote-MR review with one process:
`reviewmatic run --url <mr-url> --review-mode <fast|normal> --locale <en|ru> --incremental auto --repo-root <checkout>`. The checkout is required: ask the
user for a checkout of the reviewed repository and pass its path with
`--repo-root`; the run never clones or creates a repository for the MR. The
checkout must have a Git remote pointing at the MR's project (any remote
name; for a fork MR register the fork as a new remote with `git remote add`,
or rely on an anonymous host URL, so the exact MR head object is fetchable)
and must fetch the exact base/start/head objects. A non-checkout path, a
checkout without a matching remote, or one that cannot fetch the objects is
an instructive error naming the missing remote — never substitute silently
or clone behind it. The run owns every mechanical step — evidence, context, finalization,
scaffolding, and the report — and stops only where an agent must author an
artifact; every stop prints the template path and exact next command as
`uvx --from "$REVIEWMATIC_FROM" reviewmatic ...`.
Do not duplicate canonical collection with direct `glab mr view` or parallel
MR reads; use `--incremental off` only for an explicit request such as
"without incremental review", "start from scratch", or "ignore the previous
review" — "full review" alone is not an opt-out.

The run stops once for the panel poll. The stop carries the complete poll
presentation: `poll.text` is the verbatim question and `poll_block` is the
ready-to-copy presentation — the as-is note plus the poll inside a fenced
block. Copy the fenced `poll_block` into your response exactly as printed:
every line word for word, the fences included, without paraphrasing,
blockquoting, rewrapping, or summarizing — the block is the poll, not a draft
to restyle. The poll names the critics, the engine of every
critic, the one-line arbitrator role, and the resolved mode with an engines
note when the OCR engine is excluded (only when even the compacted background
exceeds the CLI limit; the note reports the compacted size and the cut
sections); when the note excludes OCR, do not offer it. Term meanings are
fixed in `references/poll-glossary.md`; attach your recommendation, and the
choice is the user's. Before
proposing the option variants, ground the critic pool in the host's agent
inventory (`agents/*.md` in the harness-global and project config directories, and the `agent` key of the global and project `opencode.json`): suggest more than one
model critic only when candidate agents carry distinct models or engines, and
never propose two critics on the same single model — two critics running one
model are not an independent check. An agent defined without a model runs on
the primary session's model; an inventory source that cannot be read makes
the pool unknown, not empty. Fill the
returned selection template with the answer and run the printed
`reviewmatic run --resume --url <mr-url> --participants <template>` command. A `fast` review never stops for the poll: it runs without a panel. Never
substitute a configuration silently: the recorded names appear in the results, and the state machine rejects a substituted configuration.
A pipeline transition that arrives while the poll waits — a failed job, a reddening downstream pipeline, a landed note — is post-collection drift, not a poll answer: it never restarts the run, never re-collects evidence, and never adds a second critic. The OCR background was measured before the poll, and the run executes that exact render. Finish the selection; the next resume takes a re-anchor before prose whose fingerprint comparison without persisting keeps authorship for code-identical state, and a CI-only transition becomes exactly one CI delta target checked with `record-delta` while prior checks stay in history — one fresh delta check, never a second critic. A full restart with re-collection is only for changed code or changed notes.
The emitted critic template is pre-stamped: its `run_id` already carries this reviewmatic run's identity and must not be changed, and `session_id` is the real session id of that critic subagent — never copy another critic's or the orchestrator's identity into a receipt.
After the selection the run continues mechanically. OCR critics execute
inside the run without an authoring stop: reviewmatic renders the compact
background (thread registry and open questions verbatim, judgment sections
under their byte caps — the poll measured exactly this render), invokes the
`ocr` CLI over the exact base..head range, maps the comments into one
receipt, and binds it to the selected critic. Each model critic stops the run
once: the stop names the participant, prints its ready receipt template, and
the exact `reviewmatic record-run-critic --artifact-root <root> --input <template> --participant <name>` command — launch the critic as an
independent subagent over the collected context and the managed review
worktree, fill the receipt verbatim, and run the printed command; with the
last receipt imported, the panel merges and the run continues by itself.
The remaining stops are the decision and the prose. At the decision stop,
launch the selected arbitrator in a separate native session: it verdicts every
critic finding and may record `publication_intents` (one finding ID with
`publication: {kind, fix_mode}` and optional dependencies); import the
decision with the returned `reviewmatic finalize-review` command. The run then
invokes the shared renderer, materializes `content-prose-<digest>.json`, and
returns `template_kind=prose` with `reviewmatic record-prose --artifact-root <root> --input <prose>`.
Edit prose, semantic choices, and fix payloads only. Do not author positions,
range counters, patch paths/digests, revisions, or `update_issue`.
Return the prepared `finding_id` unchanged. Never create or reconstruct machine
identities, substitute another identifier, or send unknown rows. Use
`target: {path,before}` and `replacement` for ordinary multiline fixes without
structural repair. Label rows are `{name,status,rationale}` for the complete
catalog. Recorded rejected-candidate reasons are reused, not authored again.
Thread fixes use the same semantic `target`/`replacement` or `parts` in
`thread_decisions`, with `fix_mode=suggestion`. The runtime derives their
suggestion positions too. Addressed prose updates retain other filled rows.
The runtime derives the SemVer basis and bindings. Fill only missing substantive
policy and impact assessments, never fake reasons to satisfy validation.
For a policy-specific basis select a collected publication with
`semver_assessment.basis: {name,source}`, never a SHA or reconstructed baseline.
Critics and the arbitrator read `incremental.history_context` from the returned
context path. History is advisory and may warn without blocking current review.
The runbook stands on current findings and proposals, without historical ledger
coverage, inherited IDs/revisions, or manual synchronization.
Resume the same run to finalize; `scaffold-review` is the structural repair
path, never the tail. Judge the tail rows by this file's tail rules above —
they are the complete doctrine for the run path's prose and finalize
judgments, and the repair-path stage files stay closed on the one-process run;
print the returned report through `references/output-format.md`, and execute
no publication commands. When the run reaches its final plan (`stage: plan_ready`), the
final response carries `final_checklist`: the sanctioned self-check before
reporting — progress at `plan_ready`, the runbook at the printed plan path,
every critic receipt bound, the decision recorded, the prose applied, then
hand over the response's chat summary. That checklist over the run's own
printed outputs is the complete final verification. Wanting to re-read the
stage rules, references, or contracts before reporting is the red flag the
checklist already answers: reading references after the final plan is an
out-of-stage read the reading discipline forbids.
