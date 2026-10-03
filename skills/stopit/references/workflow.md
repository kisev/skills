# Workflow

## Boundary

- Store the handoff outside the repository under the XDG state directory at the
  stable workspace-scoped path
  `$XDG_STATE_HOME/agent-skills/stopit/<workspace-id>/handoff.md`. The bundled
  runner resolves the platform default when `XDG_STATE_HOME` is unset.
- Derive `<workspace-id>` only from the canonical existing workspace path by
  using the bundled runner. Do not construct or shorten the ID manually.
- Do not change the repository, `.gitignore`, Git state, or external systems.
- Do not copy logs, secrets, personal data, or large context. Use a redacted
  summary and exact references to existing artifacts, paths, or SHA values.
- Never include session identifiers (`ses_...`), session names, or paths to
  session logs or transcripts. Reference only durable repository or build
  artifacts such as tracked paths and commit SHAs.

## Runner

The bundled runner is POSIX-only because safe traversal and workspace locking
require POSIX file-descriptor operations and `fcntl`. Lock acquisition uses
non-blocking retries with a bounded five-second deadline; contention beyond the
deadline fails without writing the handoff. A lock file with multiple hard links
is unsafe and rejected before its mode is changed or a lock is acquired.

Run from the skill directory. Before preparing content, resolve the exact
destination without writing any state:

```shell
python3 -I -S -B scripts/handoff.py path --workspace <WORKSPACE>
```

Pass the prepared content on standard input to the write command:

```shell
python3 -I -S -B scripts/handoff.py write --workspace <WORKSPACE> --expected-path <HANDOFF_PATH>
```

Provide the in-memory content through the command's standard input; do not
create a separate draft artifact. Pass the exact path returned by `path` as
`<HANDOFF_PATH>` so a changed workspace alias or state root cannot redirect the
write. The runner rejects a changed destination, missing workspaces, unsafe or
symlinked state paths, empty, invalid UTF-8, or oversized content. It creates
private directories and atomically replaces `handoff.md` with a private file. A
changed handoff retains a content-addressed, body-only snapshot; the current
file ends with paths to earlier snapshots.

## Procedure

1. Treat the supplied focus as the purpose of the next session.
2. Collect only verifiable facts from the repository, existing artifacts, and
   the whole session. The handoff covers the whole conversation from its first
   request to the end, including tasks, decisions, blockers, artifacts, and
   completed checks; separate decisions from assumptions and unresolved
   questions. Summarize briefly; do not paste raw conversation content.
3. Read the existing handoff body, everything above its `## History` footer,
   and carry forward what stays relevant: open blockers, durable decisions,
   environment constraints, and artifacts. Compress carried-forward material
   harder the older it is, and drop closed or stale items. Never read the
   footer or the snapshots it lists.
4. Prepare the draft. As needed, use the sections `Decisions`, `Current state`,
   `Blockers`, `Next steps`, `Artifacts`, and `Recommended skills`; do not add
   empty sections. Keep the body within roughly 8-16 KiB; the runner rejects
   anything beyond its hard 256 KiB limit.
5. Run the read-only `path` command. Then write the draft immediately through
   the `write` command, passing the returned path as `--expected-path`. Do not
   show the draft and do not ask for confirmation.
6. Briefly report the destination path, which data were summarized or redacted,
   and which references were retained instead of being copied.

## Result

- The handoff is usable by the next session without hidden state.
- Completed, current, next, and blocking work are explicitly separated.
- A next session restores context by resolving the path with `path` and reading
  only the handoff body above the `## History` footer; it never reads the
  footer or snapshot files.
- Repeated handoffs for the same canonical workspace atomically replace the same
  XDG state file while retaining changed versions. A workspace lock serializes
  the read, history snapshot, and replacement so concurrent writes do not lose
  versions; different canonical workspaces use different IDs.
- There are no Git or external-system changes.

## Memory integration

When restoring a handoff, optionally search personal memory (`memory_search`
tool or `memomatic search`) for durable facts about this workspace; the
handoff itself carries the transient context. Writing a handoff mirrors a
short distillate into the memomatic inbox automatically (`source: stopit`,
superseded per workspace, auto-cleaned through a `source=stopit` rule); when
memomatic is absent the mirror is skipped silently.
