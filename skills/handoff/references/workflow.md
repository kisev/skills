# Workflow

## Boundary

- Store the handoff outside the repository under the XDG state directory at the
  stable workspace- and session-scoped path
  `$XDG_STATE_HOME/agent-skills/handoff/<workspace-id>/<session-id>/handoff.md`.
  The bundled runner resolves the platform default when `XDG_STATE_HOME` is unset.
- Derive `<workspace-id>` only from the canonical existing workspace path by
  using the bundled runner. Do not construct or shorten the ID manually.
- Take `<session-id>` only from the current session ID in the host metadata.
  Never invent a session ID, guess one, or borrow another session's ID; when
  the host provides no usable session ID, stop without writing.
- Do not change the repository, `.gitignore`, Git state, or external systems.
- Do not copy logs, secrets, personal data, or large context. Use a redacted
  summary and exact references to existing artifacts, paths, or SHA values.
- Never include session identifiers (`ses_...`), session names, or paths to
  session logs or transcripts in the handoff content; this prohibition covers
  the body, not the destination path or the `--session` argument, which are the
  only sanctioned uses of the current session ID. Reference only durable
  repository or build artifacts such as tracked paths and commit SHAs.
- Parallel sessions of one workspace write separate session directories and
  never read each other's handoffs or the legacy workspace-level
  `<workspace-id>/handoff.md`.

## Runner

The bundled runner is POSIX-only because safe traversal and session-scoped
locking require POSIX file-descriptor operations and `fcntl`. Lock acquisition
uses non-blocking retries with a bounded five-second deadline; contention
beyond the deadline fails without writing the handoff. A lock file with
multiple hard links is unsafe and rejected before its mode is changed or a
lock is acquired.

Run from the skill directory. Before preparing content, resolve the exact
destination for the current session without writing any state:

```shell
python3 -I -S -B scripts/handoff.py path --workspace <WORKSPACE> --session <SESSION_ID>
```

Pass the prepared content on standard input to the write command:

```shell
python3 -I -S -B scripts/handoff.py write --workspace <WORKSPACE> --session <SESSION_ID> --expected-path <HANDOFF_PATH>
```

`<SESSION_ID>` must be the current session ID from the host metadata. The
runner accepts only a nonempty `ses_[A-Za-z0-9_-]+` token without path
separators or relative components and fails without creating state otherwise.
Provide the in-memory content through the command's standard input; do not
create a separate draft artifact. Pass the exact path returned by `path` as
`<HANDOFF_PATH>` so a changed workspace alias or state root cannot redirect the
write. The runner rejects a changed destination, missing workspaces, an absent
or invalid session ID, unsafe or symlinked state paths, empty, invalid UTF-8,
or oversized content. It creates private directories and atomically replaces
`handoff.md` with a private file inside the session directory. A changed
handoff retains a content-addressed, body-only snapshot; the current file ends
with paths to earlier snapshots.

## Procedure

1. Treat the supplied focus as the purpose of the next session; a continuation
   focus never drops earlier topics from the walkthrough.
2. Run the read-only `path` command with the current session ID to resolve the
   exact destination before reading any state.
3. Read the existing handoff only from that resolved session path, and only
   its body above the `## History` footer; when the file does not exist, this
   is the first handoff. Never read another session's handoff or the legacy
   workspace-level file. Never read the footer or the snapshots it lists.
   Carry forward what stays relevant: open blockers, durable decisions,
   environment constraints, obligations, and artifact references. Remove
   duplicates and stale statuses; closed work leaves no open items, but its
   significant outcomes stay in the walkthrough. Compress carried-forward
   material harder the older it is.
4. Collect only verifiable facts from the repository, existing artifacts, and
   the whole session. The body is a brief walkthrough of the whole conversation
   from its first request to the end: the initial goal, significant topics and
   direction changes, decisions, completed and current work, checks, blockers,
   and next actions. Separate decisions from assumptions and unresolved
   questions. Mark context lost to compaction as a gap; never invent facts.
   Summarize briefly; do not paste raw conversation content.
5. Prepare the draft. As needed, use the sections `Decisions`, `Current state`,
   `Blockers`, `Next steps`, `Artifacts`, and `Recommended skills`; do not add
   empty sections. Keep the body within roughly 8-16 KiB without padding short
   handoffs or dropping essential decisions to save space; the runner rejects
   anything beyond its hard 256 KiB limit.
6. Write the draft immediately through the `write` command, passing the same
   session ID and the path returned in step 2 as `--expected-path`. Do not
   show the draft and do not ask for confirmation; provide the in-memory
   content on standard input and do not create a separate draft artifact.
7. After a successful write, report the destination path, which data were
   summarized or redacted, and which references were retained instead of being
   copied. If the write fails, report the failure as-is and never claim
   success.

## Result

- The handoff is usable without hidden state: the same session can restore and
  rewrite it, and any other session reads it only from its full path.
- Completed, current, next, and blocking work are explicitly separated.
- The writing session restores context by resolving the path with `path` for
  its own session ID and reading only the handoff body above the `## History`
  footer; it never reads the footer or snapshot files. Any other session,
  including the next one, restores this handoff only from its full path
  explicitly passed by the user; the skill has no list, index, or
  auto-discovery of session handoffs.
- Repeated handoffs for the same workspace and session atomically replace the
  same XDG state file while retaining changed versions. A lock inside the
  session directory serializes the read, history snapshot, and replacement so
  concurrent writes of one session do not lose versions; parallel sessions of
  one workspace use different files and never merge or overwrite each other's
  histories.
- There are no Git or external-system changes.

## Memory integration

When restoring a handoff, optionally search personal memory (`memory_search`
tool or `memomatic search`) for durable facts about this workspace; the
handoff itself carries the transient context. Writing a handoff mirrors a
short distillate into the memomatic inbox automatically (`source: handoff`,
superseded per workspace and session, auto-cleaned through a `source=handoff`
rule); when memomatic is absent the mirror is skipped silently.
