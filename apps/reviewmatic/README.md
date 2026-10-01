# reviewmatic

[Русская версия](README.ru.md)

`@kisev/reviewmatic` is the executable runtime of the `code-review` skill: the
complete review chain (GitLab evidence collection, the review state machine,
immutable plans, guarded publication) plus an interactive terminal walkthrough
of a finished review plan.

## Install

```bash
npm install --global @kisev/reviewmatic
```

Requires Node.js 22.13+ and the `glab` CLI authenticated for your GitLab host.
When using the dev skill distribution, install `@kisev/reviewmatic@dev` rather
than the stable npm channel. If OpenCode has the agentomatic core plugin, update
that package too and restart OpenCode: updating the CLI alone does not reload
native subagent routing hooks. Additional agent profiles are still optional.
Review state lives under `$XDG_STATE_HOME/agent-skills/gitlab/<target-key>/`, the same
layout the review commands write.

## Review chain

Agents use one editable draft, without copying bindings between decision and
content files:

```bash
reviewmatic start-review --url <mr-url> --repo-root <checkout> --review-mode normal --locale en
reviewmatic check-review --draft <draft-path>
reviewmatic finish-review --draft <draft-path>
```

`start-review` collects evidence and context and returns the draft, exact-commit
inspection snapshots, and an independent critic receipt template. The host agent
does the review and launches native subagents. Optional specialist critics can be
selected by count and profile; without them, ordinary independent subagents are
supported. `critic_count` records the chosen count, and `critics` contains their
actual receipts. Primary findings and critic candidates receive one disposition
each. The runner derives accepted findings, rejected candidates, verdicts, and
artifact bindings; the agent supplies the semantic assessments, concrete fixes,
label rationales, and thread outcomes.

`check-review` is local: it returns field paths and errors without recollecting
GitLab or freezing decisions. Edit the same draft and check again. `resume-review --artifact-root <root>` recovers that draft after interruption without remote
collection. `finish-review` validates it, rechecks complete evidence and context
once, and atomically updates the final plan, Markdown, and baseline. Stale inputs
leave the draft and previous final plan intact; run `start-review` again when the
MR changed. Collection, validation, and finalization timings are returned
separately from host model/subagent time. Existing v2 artifacts and the low-level
`prepare`/`context`/`template-review` commands remain supported; do not mix the two
workflows in one review.

Local work-in-progress reviews use `prepare-local` and `finalize-local`;
`status`, `next`, and `assess-mode` inspect progress. Every command prints a
compact JSON result and never mutates GitLab or the checkout.

## Interactive plan walkthrough

After a review the agent prints a short summary plus one command:

```bash
reviewmatic plan --artifact-root <root>
```

Run it manually in your terminal. Existing threads show the remark, the drafted
reply, the complete conversation, assessment, rationale, and GitLab link, even
when no publication is proposed. Use arrows or `j`/`k` to select and scroll,
Page Up/Down for longer lists and conversations, and left/right to move between
items. Links are clickable in terminals supporting OSC 8; `o` opens the selected
discussion in a browser. Enter opens an item and never publishes it.

Press `s` to send only the reply or `S` to send it with the planned resolve/reopen
action, then confirm with `y`. Escape cancels confirmation or returns to the list.
Read-only items offer no send/edit action. Press `e` to edit
the draft in `$EDITOR`; the plan is amended to the edited body before anything
is sent, with the Markdown and baseline updated together. Editing a patch body
must preserve its validated patch and command. New threads, recommended issues,
and label updates use the same
walkthrough. Suggestions and git patches additionally offer local application:
reviewmatic creates a dedicated git worktree at the exact reviewed head, shows
the diff, and then asks for commit and push as two separate confirmations.

Every send goes through the guarded publication contract
(`reviewmatic publication apply/inspect/retry`): actions bind the GitLab user,
MR refs, conversation, and body digests; receipts make retries idempotent; an
uncertain outcome blocks only its own action and offers read-only inspection
before an explicit retry.

## Worktree registry

Created worktrees are recorded in
`$XDG_STATE_HOME/agent-skills/reviewmatic/worktrees.json`. Nothing is deleted
automatically; `reviewmatic worktree list` prints the registry with commit and
push state per worktree.

## Compatibility contract

Existing v2 plans and single-critic receipts remain readable. Multi-critic
receipts add optional `contributors` and require the updated runtime; the shared
schema and TS copy are checked together. Canonical JSON and digests are validated
against the Python reference in tests.
The package creates no state on `--help` or `--version`.
