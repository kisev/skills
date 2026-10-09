# Run path: the primary remote-MR review

Drive a remote-MR review with one process: `reviewmatic run --url <mr-url> --review-mode <fast|normal> --locale <en|ru> --incremental auto`. `--repo-root <checkout>` is optional and uses the same resolution as `start-review`: a matching checkout is an optimization, and a missing or object-less checkout falls back to the managed clone. The run verifies the exact base and head objects during context collection and stops with a concrete error otherwise. The run owns every mechanical step — evidence collection, context, finalization, scaffolding, and the final report — and stops only where an agent must author an artifact. Every stop prints the ready template path and the exact next command; execute each returned command as `uvx --from "$REVIEWMATIC_FROM" reviewmatic ...`.
The run stops once for the panel poll. The stop carries the complete poll
presentation under `poll`: `poll.text` is the verbatim question, keyed to the
review locale, and the stop's `rules` instruct how to present it — present the text
word for word, without paraphrasing or summarizing; never retell the template
in your own words. The poll names the critics, the engine of every critic, the
one-line arbitrator role, and the resolved mode with an engines note when the
OCR engine is excluded (only when even the compacted background exceeds the
CLI limit; the note reports the compacted size and the cut sections); when
the note excludes OCR, do not offer it. The term meanings are
fixed in `references/poll-glossary.md`. Attach your recommendation to the poll; the choice is the user's. Before
proposing the option variants, check the installed critic profiles with
`agentomatic agent list` (or the profile manifest): propose more than one
model critic only when installed profile critics with distinct models or
engines exist, and never propose two critics on the same single model — two
critics running one model are not an independent check; with an empty critic
pool the honest composition is one subagent on the current model plus the
arbitrator. Fill the
returned selection template with the answer and run the printed
`reviewmatic run --resume --url <mr-url> --participants <template>` command. A `fast` review never stops for the poll: it runs without a panel. Never
substitute a configuration silently: the recorded names appear in the results, and the state machine rejects a substituted configuration.

A pipeline transition that arrives while the poll waits — a job moves from running to failed, a downstream pipeline reddens, a note lands — is post-collection drift, not a poll answer: it never restarts the run, never re-collects evidence, and never adds a second critic. The OCR background was measured before the poll, and the run executes that exact render. Finish the selection; the next resume takes a re-anchor before prose, whose fingerprint comparison without persisting keeps authorship for code-identical state, and a CI-only transition becomes exactly one CI delta target checked with `record-delta` while prior checks stay in history — one fresh delta check, never a second critic. A full restart with re-collection is only for changed code or changed notes.

The emitted critic template is pre-stamped: its `run_id` already carries this reviewmatic run's identity and must not be changed, and `session_id` is the real session id of that critic subagent — never copy another critic's or the orchestrator's identity into a receipt.

After the selection is recorded the run continues mechanically. OCR critics execute inside the run without any authoring stop: reviewmatic renders the compact background from the collected context (thread registry and open questions verbatim, the judgment sections under their byte caps — the poll measured exactly this render), invokes the `ocr` CLI over the exact base..head range, maps the comments into one receipt, and binds it to the selected critic. Model critics stop the run once each: the stop names the participant, prints its ready receipt template, and the exact `reviewmatic record-run-critic --artifact-root <root> --input <template> --participant <name>` command. Launch the model critic as an independent subagent over the collected context and the managed review worktree described below, fill its receipt template verbatim, and run the printed command; when the last receipt is imported, the panel merges into one aggregate critic receipt and the run continues by itself.
The remaining stops are the decision and the prose. At the decision stop,
launch the selected arbitrator in a separate native session. It verdicts every
critic finding and may record `publication_intents`: one finding ID with
`publication: {kind, fix_mode}` and optional dependencies and source target.
Import the decision with the returned `reviewmatic finalize-review` command.
The real `run` then invokes the shared renderer, materializes
`content-prose-<digest>.json`, and returns `template_kind=prose` with
`reviewmatic record-prose --artifact-root <root> --input <prose>`.
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
path, never the normal tail. Apply the discussion, findings, SemVer, and
metadata doctrine below to those judgments. Print the returned report through
`references/output-format.md`, and execute no publication commands.
