# `skill-doctor`

## Purpose

Diagnose skill usage of the current session on an explicit request, keep the
experience in private incremental XDG diagnoses, reuse it during development,
and prepare a public bug-report archive after a separate confirmed request.

## Triggers and Near-Misses

Trigger for an explicit diagnosis, matching, or bug-report request; near-miss:
routine skill use, static skill audits without session history, and automatic
post-change runs. The skill never triggers by itself.

## Inputs and Outputs

Input is the current session identifier with the host session history, and for
matching the current skill sources. Output is a private per-session diagnosis
record under `$XDG_STATE_HOME/agent-skills/skill-doctor/sessions/<key>/`, a
read-only match report against current sources, and, only after a separate
confirmed request, a self-contained anonymized archive under
`$XDG_STATE_HOME/agent-skills/skill-doctor/reports/<report-id>/`. Transfer of
the archive stays manual.

## Workflow Stages

Resolve the exact current session and collect its evidence read-only; classify
difficulties as skill defects, environment problems, or agent execution;
merge with the stored diagnosis by stable observation identifiers with
append-only evidence; record through the runner with a content-addressed
history; match recorded defects against current sources by declared origin and
code fingerprints; preview the public archive completely and write it after
explicit confirmation bound to the previewed destination.

## Dependencies

Host session databases (opencode, kilo, mimo), the private XDG state root,
current skill sources for matching, and the shared private-state and portable
runtime contracts.

## Remote/Local Effects

Read-only host database access; private atomic writes only under the
skill-doctor XDG root; no repository, network, or external-system effects, and
no modification of skill sources.

## Errors, Partial, Escalation

An unreliable current session identifier, a missing session, or a session in
another host stops the diagnosis instead of substituting another session.
Incomplete or truncated history is recorded as explicit coverage notes. The
runner refuses public archives that contain any declared private value, a
changed destination, or an existing archive with different content.

## Unique Constraints

Suspected and confirmed causes stay separated, evidence is never presented as
a confirmed cause without support, and evidence entries are append-only across
revisions. A matching skill name alone never proves identity when the recorded
origin is ambiguous. The public archive never carries conversation history,
raw logs, project files, private diagnoses, or the anonymization mapping, and
its file names and metadata stay neutral.

## Requirement

### REQ-F-549 - Keep current-session diagnoses evidence-based and incremental

The skill shall diagnose only the session with the explicitly identified
identifier, shall record observations with cited evidence, explicit
classification (skill defect, environment, agent execution), and suspected
versus confirmed status, and shall store each session's diagnosis in a private
XDG record that repeated invocations extend without duplicate observations and
without dropping or rewriting recorded evidence, while replaced versions stay
in a content-addressed history. Coverage of the analyzed history shall be
recorded explicitly, including incompleteness notes. Matching shall verify
recorded code fingerprints and the recorded origin against current sources and
shall report relevant, resolved, unclear, or needs-clarification verdicts,
where an ambiguous origin yields needs-clarification even when the skill name
matches, and shall not modify sources.

#### Verification

Fixture-database and state-root tests assert exact-session selection without
substitution, coverage notes for partial history, per-session isolation,
append-only incremental recording with history snapshots, and fingerprint and
provenance verdicts including the ambiguous-origin refusal.

### REQ-F-550 - Confine the public bug-report archive to confirmed anonymous content

The skill shall build a public archive only after preview and explicit
confirmation bound to the exact previewed destination; the archive shall be
self-contained (identification with explicit unknown version marking, expected
and actual behavior, minimal anonymized example, known workaround,
recommendations, and a machine manifest marking unknown versions and unverified
reproduction), shall exclude conversation history, raw session logs, project
files, private diagnoses, and the anonymization mapping, shall refuse declared
private values in content or file names, and shall use neutral file names with
neutralized timestamps. Transfer remains a manual user action.

#### Verification

Runner tests assert preview-to-archive equality, refusal of declared private
values, refusal of a changed destination and of conflicting rewrites, explicit
unknown-version and unverified-reproduction marking, and neutralized file
metadata.

## Example

`skill-doctor` records a workaround for a misdiagnosed skill error in one
session, later reports it as still relevant against the unchanged source, and
separately prepares a confirmed archive for an upstream issue.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
