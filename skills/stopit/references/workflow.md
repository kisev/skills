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

## Runner

Run from the skill directory. Before preparing or showing the draft, resolve the
exact destination without writing any state:

```shell
python3 -I -S -B scripts/handoff.py path --workspace <WORKSPACE>
```

After explicit confirmation, pass the exact approved draft on standard input:

```shell
python3 -I -S -B scripts/handoff.py write --workspace <WORKSPACE> --expected-path <CONFIRMED_PATH>
```

Provide the already approved in-memory content through the command's standard
input; do not create a separate draft artifact. Pass the exact path returned by
the preview as `<CONFIRMED_PATH>` so a changed workspace alias or state root
cannot redirect the approved write. The runner rejects a changed destination,
missing workspaces, unsafe or symlinked state paths, empty, invalid UTF-8, or
oversized content. It creates private directories and atomically replaces
`handoff.md` with a private file.

## Procedure

1. Treat the supplied focus as the purpose of the next session.
2. Collect only verifiable facts from the conversation, repository, and existing
   artifacts. Separate decisions from assumptions and unresolved questions.
3. Prepare a new draft. As needed, use the sections `Decisions`, `Current state`,
   `Blockers`, `Next steps`, `Artifacts`, and `Recommended skills`; do not add
   empty sections.
4. Run the read-only `path` command. Show the complete draft and its exact output
   path, then obtain explicit confirmation before writing.
5. After confirmation, send exactly the approved draft and confirmed path to the
   `write` command. Do not create a separate draft file. Briefly report which data
   were summarized or redacted and which references were retained instead of being
   copied.

## Result

- The handoff is usable by the next session without hidden state.
- Completed, current, next, and blocking work are explicitly separated.
- Repeated handoffs for the same canonical workspace atomically replace the same
  XDG state file; different canonical workspaces use different IDs.
- There are no Git or external-system changes.
