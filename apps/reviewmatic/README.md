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
Review state lives under `$XDG_STATE_HOME/agent-skills/code-review/`, the same
layout the review commands write.

## Review chain

Agents drive a review through the same commands the skill references:

```bash
reviewmatic prepare --url <mr-url> --repo-root <checkout> --review-mode normal --locale en
reviewmatic context --evidence <path> --repo-root <checkout>
reviewmatic template-review --artifact-root <root> --kind critic
reviewmatic record-artifact --kind critic_receipt --evidence <path> --input <path>
reviewmatic finalize --artifact-root <root>
reviewmatic finalize-review --evidence <path> --report <path> --mode normal \
  --finalize-report <path> --context <path>
reviewmatic scaffold-review --evidence <path> --context <path> --decision <path> --content <path>
reviewmatic report-review --artifact-root <root>
```

Local work-in-progress reviews use `prepare-local` and `finalize-local`;
`status`, `next`, and `assess-mode` inspect progress. Every command prints a
compact JSON result and never mutates GitLab or the checkout.

## Interactive plan walkthrough

After a review the agent prints a short summary plus one command:

```bash
reviewmatic plan --artifact-root <root>
```

Run it manually in your terminal. Existing threads show the remark, the drafted
reply, and explicit choices: send, send and resolve, or skip. Press `e` to edit
the draft in `$EDITOR`; the plan is amended to the edited body before anything
is sent. New threads, recommended issues, and label updates use the same
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

Digests and artifacts stay byte-compatible with the documented v2 artifact
contracts; canonical JSON is validated against the Python reference in tests.
The package creates no state on `--help` or `--version`.
