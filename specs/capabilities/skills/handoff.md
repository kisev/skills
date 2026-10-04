# `handoff`

## Purpose

Create an anonymized handoff for the next session in stable workspace- and
session-scoped XDG state.

## Triggers and Near-Misses

Trigger when pausing or changing context; near-miss: committing project notes.

## Inputs and Outputs

Input is current session context, the current session identifier, and an
existing workspace. Output is a redacted handoff with facts and next step under
the XDG state directory at
`$XDG_STATE_HOME/agent-skills/handoff/<workspace-id>/<session-id>/handoff.md`;
the runner uses the platform default state directory when the variable is unset.

## Workflow Stages

Resolve the canonical workspace, the validated session, and the destination
read-only, redact, accumulate relevant context only from the same session's
existing handoff body, prepare the draft, write it immediately without preview
or confirmation while binding the write to the resolved path, report the
destination and applied redactions.

## Dependencies

Current session and its identifier, existing workspace, XDG state directory,
and POSIX file descriptor traversal and `fcntl` locking.

## Remote/Local Effects

Privately and atomically replaces only the stable session handoff, without a
preview or confirmation gate, and retains changed body-only versions in
content-addressed XDG history inside the session directory; no repository or
remote effects.

## Errors, Partial, Escalation

Redaction uncertainty, invalid input, a missing or invalid session identifier,
or an unsafe or symlinked state path blocks handoff creation. Unsupported
platforms or unavailable `fcntl` locking produce a controlled error rather than
an import failure. Lock contention is retried non-blockingly only until a
bounded deadline, then fails without writing.

## Unique Constraints

Handoff is not a repository artifact and must not expose private reasoning. The
workspace ID is a deterministic digest of the canonical existing workspace path.
The session ID is supplied by the host for the current session only, and runs
never read, write, or remove the legacy workspace-level handoff file.

## Requirement

### REQ-F-121 - Keep handoffs stable, session-scoped, and redacted

The skill shall resolve the exact destination read-only for the current
workspace and session, write the prepared content immediately without preview
or confirmation while binding the write to the resolved path, and report the
destination and applied redactions afterward. The destination shall be
`$XDG_STATE_HOME/agent-skills/handoff/<workspace-id>/<session-id>/handoff.md`,
where the workspace ID is the deterministic digest of the canonical existing
workspace path and the session ID is a nonempty `ses_[A-Za-z0-9_-]+` token
without path separators or relative components; a missing or invalid session ID
shall produce a controlled error without creating state. Each handoff shall
cover the whole session from its first request to the end, carry forward
relevant context only from the same session's existing handoff body above its
`## History` footer, and reference only durable repository or build artifacts
without session identifiers, session names, or session log or transcript paths.
The runner shall write only bounded, nonempty, valid UTF-8 content to the
designated session-scoped XDG state file, reject changed destinations, unsafe
and symlinked state paths, and use private directories, a private file, and
atomic replacement without creating a separate draft artifact. The current file
shall list only paths to earlier body-only snapshots after its latest handoff,
and history shall accumulate only within its own session directory. A lock
inside the session directory shall serialize stable-file reads, history
creation, and replacement so concurrent successful writes of one session retain
every version, and lock acquisition shall use non-blocking bounded retries. The
runner shall reject a lock file whose link count is not exactly one before
changing its mode or acquiring its lock, and shall never read, write, or remove
the legacy workspace-level handoff file.

#### Verification

Handoff tests verify session isolation, workspace isolation, redaction, stable
state history, safe paths, unchanged legacy files, and unchanged project files;
the handoff retains blockers and next actions.

## Example

`handoff` records a blocker and next step for one canonical workspace and the
current session without copying secrets or chain of thought.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
