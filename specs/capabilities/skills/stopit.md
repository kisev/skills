# `stopit`

## Purpose

Create an anonymized handoff for the next session in stable workspace-scoped XDG state.

## Triggers and Near-Misses

Trigger when pausing or changing context; near-miss: committing project notes.

## Inputs and Outputs

Input is current session context and an existing workspace. Output is a redacted
handoff with facts and next step under the XDG state directory at
`$XDG_STATE_HOME/agent-skills/stopit/<workspace-id>/handoff.md`; the runner uses
the platform default state directory when the variable is unset.

## Workflow Stages

Resolve the canonical workspace and destination read-only, redact, show the full
draft and exact path, confirm, require that path as the write binding, atomically
write the approved standard input, report.

## Dependencies

Current session, existing workspace, XDG state directory, and POSIX file
descriptor traversal and `fcntl` locking.

## Remote/Local Effects

After explicit confirmation, privately and atomically replaces only the stable
workspace handoff and retains changed body-only versions in content-addressed
XDG history; no repository or remote effects.

## Errors, Partial, Escalation

Redaction uncertainty, invalid input, or an unsafe or symlinked state path blocks
handoff creation. Unsupported platforms or unavailable `fcntl` locking produce a
controlled error rather than an import failure. Lock contention is retried
non-blockingly only until a bounded deadline, then fails without writing.

## Unique Constraints

Handoff is not a repository artifact and must not expose private reasoning. The
workspace ID is a deterministic digest of the canonical existing workspace path.

## Requirement

### REQ-F-121 - Keep handoffs stable, scoped, and redacted

The skill shall preview the complete draft and exact read-only-resolved path,
require explicit confirmation and the same path as the write binding, and then
write only bounded, nonempty, valid UTF-8 approved content to the designated
workspace-scoped XDG state file. The runner shall reject changed destinations,
unsafe and symlinked state paths and use private directories, a private file, and
atomic replacement without creating a separate draft artifact. The current file
shall list only paths to earlier body-only snapshots after its latest handoff.
A workspace lock shall serialize stable-file reads, history creation, and
replacement so concurrent successful writes retain every version, and lock
acquisition shall use non-blocking bounded retries. The runner shall reject a
lock file whose link count is not exactly one before changing its mode or
acquiring its lock.

## Example

`stopit` records a blocker and next step for one canonical workspace without
copying secrets or chain of thought.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
