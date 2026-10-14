# Targeted repair and refresh

Choose the repair path by cost: the cheapest path that honestly covers the
change is the right one, and a more expensive path never runs first.

For the normal `run` tail, edit the generated prose and apply it with
`reviewmatic record-prose --artifact-root ROOT --input PROSE`; never rewind
or refresh merely to fix wording, and when the head moves the run preserves
authorship and requests a separate `record-delta` verification instead.
Refuted, changed, or ambiguous conclusions need addressed judgment or target
edits, not a repeat of panel → decision → content.

1. **Publication or arbitration texts (the cheapest honest path).** Wrong or
   improved publication prose, thread replies, or arbitration wording with
   unchanged decisions: launch a fresh arbitrator session, have it author a
   fresh arbitration receipt that keeps every decision identical
   (`merge_verdict`, findings, dispositions, CI assessments, owner reasons,
   question verifications) and changes only the content texts, and import it
   with `reviewmatic record-arbitration --draft DRAFT --input RECEIPT`. The
   import is atomic, rewinds nothing, and the runtime rejects a receipt that
   changes a decision under this path. In the run path the same texts are
   re-authored at the decision or content stop and re-imported with the
   printed commands.
2. **Critic content checked before arbitration.** A critic receipt whose
   content needs correction before the panel is arbitrated: in the run path
   replace the aggregate receipt with `reviewmatic replace-artifact --artifact-root ROOT --kind critic_receipt --path FILE`; the response prints
   the rewound stage and the exact continuation — continue from the finalize
   stage with the printed `run --resume` command, and the machine rebuilds
   everything downstream; in the draft path a recorded receipt is never edited
   in place — run `reviewmatic refresh-review --draft DRAFT` and import fresh
   receipts, because the panel selection is fixed once receipts exist.
3. **Post-plan texts.** Wording, layout, commands, positions, or fix
   representation of a finalized plan: `reviewmatic repair-review --artifact-root ROOT --kind presentation` (below). Changed decisions of a
   finalized plan: `--kind decision`.
4. **Changed evidence.** Only changed MR facts (head, discussions, metadata,
   CI) take `reviewmatic refresh-review --draft DRAFT`; never a refresh for
   text fixes.

For a finalized guided plan
`reviewmatic repair-review --artifact-root ROOT --kind presentation|fix|decision`
returns one editable draft from the finalized source. Older plans are historical only — never migrate them or execute guarded
actions — and a repair updates `runbook.md` atomically without publishing.

Record `repair.rationale` and `repair.checks`; compare the original and new
meaning yourself, since structural checks do not prove semantic equivalence.
No confirmation is needed for ordinary local edits; the user controls
publication.

- `presentation`: wording with unchanged claims and requirements, layout, commands,
  positions, or fix representation. Changed fix representation must produce the
  same complete tree, including file modes, on the exact reviewed revision.
- `fix`: a different correction of an already confirmed problem. Inspect affected
  consumers and failure paths and run relevant tests. No new critic is mandatory.
- `decision`: changed findings, risk assessments, requirements, or verdict. Obtain
  a new independent targeted critic in `critics`, update `critic_count`, and give
  every candidate an explicit disposition. For a panel plan also import a fresh
  arbitration receipt from a new arbitrator session with `record-arbitration`;
  the panel selection itself stays fixed. Do not repeat unrelated review scope.

If meaning is uncertain, use decision repair. When needed checks or evidence
are unavailable, stop, report the exact limitation, and preserve the current
plan and unfinished draft; never expand to a broad review or invent checks.
Run `check-review`, repair the same draft, then `finish-review`.

After a runtime update, use presentation repair to regenerate broken commands
in an existing contract-7 plan, keeping findings, fixes, positions, and
critic receipts unchanged and recording the comparison in `repair.checks`;
check the new body previews and commands, especially grouped suggestions.
This path is local and needs no new full review; never edit immutable action
artifacts.

For changed MR facts use `reviewmatic refresh-review --draft DRAFT`, not a new empty review.
The runner retains findings and dispositions and updates current thread bindings;
a panel plan keeps its selected participants without receipt bindings and expects
fresh critic receipts plus a fresh arbitration receipt against the refreshed
package. Reassess the reported delta and affected consumers. Old critic receipts
remain in the old draft and are never rebound by replacing digests. Obtain real
independent coverage when the changed analysis scope requires it. The context
package template is materialized prefilled from the recorded package — goal,
criteria, claims, constraints, background, and questions carried verbatim, the
binding and thread registry refreshed by the machine, `supersedes` preset to the
previous package digest, and the printed package contract naming the stale
threads: update entries that cite stale threads or changed evidence, keep the
rest, and run the printed record-package command; the runtime reports the
previous package and re-stamps question context bindings on record.

Finalization itself no longer contacts GitLab: a CI-only or material drift after
preparation is caught by an explicit `refresh-review` and by the head check that
guards every manual publication block, never by a final remote read.
