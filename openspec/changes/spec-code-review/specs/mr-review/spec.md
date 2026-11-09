# Spec Delta

## Purpose

`mr-review` reviews one GitLab merge request against a confirmed task boundary: it collects exact MR context, runs the external OpenCodeReview engine, answers whether the implementation solves the task, and produces a human runbook whose GitLab draft notes the reviewer edits and publishes.

## ADDED Requirements

### Requirement: One exact merge request target

The skill SHALL accept exactly one GitLab merge request URL as its target and SHALL NOT search for a merge request by branch name or review local working-tree changes.

#### Scenario: Branch name is not a target

- **WHEN** the request names only a branch and no merge request URL
- **THEN** the skill stops and asks for the exact merge request URL

#### Scenario: One target only

- **WHEN** the request names several merge request URLs
- **THEN** the skill asks for one target and does not review any of them yet

### Requirement: Release merge requests route to release review

The skill SHALL route a merge request that publishes or tags a version to the `release-review` skill unless the user explicitly asks for `mr-review` as well.

#### Scenario: Release MR

- **WHEN** the merge request publishes or tags a version
- **THEN** the skill routes to `release-review` and does not run the normal review

### Requirement: Read-only exact collection

The skill SHALL collect the merge request, diff, discussions, pipelines, and linked issues through read-only GitLab API calls and SHALL bind every result to the exact base, start, and head revisions.

#### Scenario: Successful collection

- **WHEN** collection completes
- **THEN** the context records the exact revisions and a completeness status

#### Scenario: No remote mutation

- **WHEN** collection runs
- **THEN** it performs no write, clone, branch, or worktree lifecycle operation through GitLab

### Requirement: Incomplete collection is explicit

The skill SHALL mark the review partial or blocked when required pages, traces, discussions, or objects are unavailable, and SHALL name the missing input instead of treating absence as evidence.

#### Scenario: Failed page

- **WHEN** a required page or endpoint fails
- **THEN** the context records the failure and the review reports partial or blocked

#### Scenario: Missing discussion

- **WHEN** a discussion cannot be read
- **THEN** the runbook names it as unverified and does not claim the conversation was reviewed

### Requirement: Task context comes from GitLab

The skill SHALL build the task baseline from the linked issues' title, description, labels, and state, the merge request description, and the human's answers; it SHALL NOT read or assess OpenSpec changes.

#### Scenario: Linked issue

- **WHEN** the merge request closes an issue
- **THEN** the issue description, labels, and state are part of the baseline

#### Scenario: OpenSpec present

- **WHEN** the repository contains an OpenSpec change
- **THEN** the skill does not read or assess it

### Requirement: The task baseline is confirmed

The skill SHALL present the goal, acceptance criteria, constraints, and open questions to the human once and SHALL record the confirmation or correction before running the review.

#### Scenario: Unknown goal

- **WHEN** the goal cannot be established from GitLab context or the human's answer
- **THEN** the baseline records it as unknown and the fulfillment verdict cannot be solved

### Requirement: Fulfillment is the central question

The skill SHALL answer whether the implementation solves the agreed task with one verdict — solved, partially, or not solved — supported by evidence and naming every uncovered criterion.

#### Scenario: Partial implementation

- **WHEN** only part of the acceptance criteria is satisfied
- **THEN** the verdict is partially and the uncovered criteria are named

#### Scenario: Not solved

- **WHEN** the implementation does not solve the task
- **THEN** the verdict is not solved and the consequence is stated

### Requirement: Baseline doubts are explicit

The skill SHALL record a doubt about the task statement separately from code findings, naming the ambiguity, the possible readings, and who decides, and SHALL NOT re-plan the task.

#### Scenario: Contradictory sources

- **WHEN** the issue and the merge request description state different goals
- **THEN** the doubt names both readings and asks the human to decide

### Requirement: One startup round then autonomy

The skill SHALL ask all user questions in one round immediately after collection — the OCR model or models and effort, and the task baseline — and SHALL run without further user interaction until the final report.

#### Scenario: After the round

- **WHEN** the startup round is answered
- **THEN** OCR runs, merging, and the runbook complete without another question

#### Scenario: No mode question

- **WHEN** the review starts
- **THEN** the skill does not ask the human to choose a clean or incremental mode

### Requirement: Review profiles define reviewers

The skill SHALL read reviewer aliases from `~/.reviewmatic/reviewers.json` and `./.reviewmatic/reviewers.json`, with the local file overlaying the global one by alias and default.

#### Scenario: Local overlay

- **WHEN** both files define the same alias
- **THEN** the local entry is used

#### Scenario: No profile

- **WHEN** neither file exists
- **THEN** the skill uses the OCR-configured default or asks for a one-off provider and model

### Requirement: Profiles never contain secrets

The profile SHALL contain only aliases, provider names, model names, and effort; the skill SHALL NOT read `~/.opencodereview/config.json` or any other file that holds credentials.

#### Scenario: Secret file

- **WHEN** OCR credentials exist in its own configuration
- **THEN** the skill does not open or copy that configuration

#### Scenario: Saving an alias

- **WHEN** the human saves a one-off model choice
- **THEN** only the alias, provider, model, and effort are written

### Requirement: OCR is the only review engine

The skill SHALL obtain every code finding from the external `ocr` CLI and SHALL NOT run an in-house critic, subagent reviewer, or arbitrator.

#### Scenario: OCR unavailable

- **WHEN** `ocr` is missing or fails
- **THEN** the skill reports the failure and stops without substituting its own review

### Requirement: Minimum OCR version

The skill SHALL require `ocr` at the minimum tested version 1.13.6 and SHALL print the install or upgrade command when the version is lower.

#### Scenario: Old OCR

- **WHEN** the installed version is below 1.13.6
- **THEN** the skill stops with the upgrade instruction

### Requirement: Parallel OCR runs

The skill SHALL run one OCR process per selected alias, in parallel when several are selected, each writing its own output.

#### Scenario: Two aliases

- **WHEN** the human selects two aliases
- **THEN** two OCR processes run and the manager merges their findings

### Requirement: The OCR background is bounded

The skill SHALL pass OCR a Markdown background file no larger than 8000 bytes, authored from the confirmed baseline and the collected context, with the task and acceptance criteria first and every truncation disclosed.

#### Scenario: Oversized context

- **WHEN** the full context exceeds 8000 bytes
- **THEN** the background keeps the task first, discloses the cuts, and the manager keeps the full context

### Requirement: The manager never reviews

The manager SHALL NOT add code findings; a suspicion SHALL become a question without severity or one additional OCR run with a narrower background.

#### Scenario: Manager suspicion

- **WHEN** the manager suspects a defect that OCR did not report
- **THEN** it records a question or runs another OCR pass and creates no finding

### Requirement: The manager arbitrates merged runs

When several OCR runs are selected, the manager SHALL merge their findings, record the reason for every duplicate or downgrade, and SHALL NOT drop a finding silently.

#### Scenario: Conflicting severities

- **WHEN** two runs report the same defect at different severities
- **THEN** the merged finding records the chosen severity and the reason

### Requirement: OCR sessions provide incrementality

The skill SHALL treat every OCR run as a persisted session; a follow-up SHALL run a fresh pass over the current range and compare it with the previous session.

#### Scenario: Previous session

- **WHEN** a prior session exists for the merge request
- **THEN** the runbook groups current findings as new, persisting, resolved, or not reviewed

#### Scenario: Interrupted run

- **WHEN** an OCR run is interrupted
- **THEN** a resume continues that session

### Requirement: The runbook format is preserved

The skill SHALL produce the existing runbook sections and SHALL change only the sections named in this specification.

#### Scenario: Unlisted section

- **WHEN** a runbook section is not named in this specification
- **THEN** its format and meaning stay as they are

### Requirement: The runbook has a task fulfillment block

The runbook SHALL contain a Task fulfillment block with the verdict, the evidence, and every uncovered criterion.

#### Scenario: Not solved

- **WHEN** the implementation does not solve the task
- **THEN** the block names the unmet criteria and the consequence

### Requirement: The runbook lists OCR runs

The runbook SHALL list each OCR run with its alias, provider, model, and effort; the arbitration section SHALL appear only when several runs were merged.

#### Scenario: One run

- **WHEN** one OCR run was selected
- **THEN** no arbitration section is produced

### Requirement: The runbook omits label and metadata advice

The runbook SHALL NOT contain project-label recommendations or MR metadata recommendations (title, description, workflow state, milestone, overall).

#### Scenario: Project labels

- **WHEN** the merge request has project labels
- **THEN** the runbook does not propose a label delta

### Requirement: Checks are simplified

The runbook SHALL report the pipeline status, failed jobs one line each, what the OCR runs covered, and what stayed unverified, and SHALL NOT classify every failed job by trace.

#### Scenario: Failed job

- **WHEN** a CI job failed
- **THEN** the runbook names it in one line without a per-trace classification

### Requirement: Draft notes are the only publication surface

The runbook SHALL end with one non-interactive shell block that creates GitLab draft notes, positioned where a position derives and general otherwise, and SHALL NOT contain a publish command.

#### Scenario: Publishing

- **WHEN** the human wants to publish
- **THEN** they do it in the GitLab UI, not from the runbook

### Requirement: The draft block checks the head

The draft block SHALL start with one check that the merge request head still matches the reviewed head and SHALL stop before creating drafts on a mismatch.

#### Scenario: Moved head

- **WHEN** the head changed after collection
- **THEN** the block exits without creating a draft

### Requirement: Thread replies are substantive

The skill SHALL prepare a reply for every open discussion where one is needed, and for a closed discussion only when the problem is still relevant, paired with a reopen.

#### Scenario: Open thread

- **WHEN** an open discussion raises a still-present problem
- **THEN** a substantive reply is prepared without a code suggestion

#### Scenario: Closed thread still relevant

- **WHEN** a closed discussion's problem is still present on the current head
- **THEN** a reply is prepared with a reopen

#### Scenario: Closed thread resolved

- **WHEN** a closed discussion's problem is no longer present
- **THEN** no reply is prepared

### Requirement: Replies use the user's voice

Every reply SHALL be written from the authenticated user's first person and factual role, SHALL use the whole discussion as context, SHALL answer the latest relevant point first, and SHALL NOT invent actions, decisions, or reactions.

#### Scenario: Addressed question

- **WHEN** the thread ends with a question to the user
- **THEN** the reply answers that question first

#### Scenario: No fabricated action

- **WHEN** the user did not perform an action mentioned in the discussion
- **THEN** the reply does not claim the user performed it

### Requirement: Reply rules are bundled

The skill SHALL carry its reply and clarity rules inside its own archive and SHALL NOT require the `humanize` or `eli5` skills to be installed.

#### Scenario: Missing skills

- **WHEN** neither `humanize` nor `eli5` is installed
- **THEN** replies still follow the bundled rules

### Requirement: The chat report describes the process

The final chat report SHALL describe collection, OCR runs, merging, limitations, artifact paths, and the next step, and SHALL NOT contain the merge request verdict or assessment.

#### Scenario: Report

- **WHEN** the review finishes
- **THEN** the chat lists the runs and limitations and leaves the verdict in the runbook

### Requirement: The runtime is a helper

The runtime SHALL provide collection, background assembly, draft-command generation, freshness revalidation, profile loading, and runtime identity; it SHALL NOT validate semantic content or enforce a workflow stage machine.

#### Scenario: Runbook prose

- **WHEN** the runbook prose is written
- **THEN** the runtime neither rejects nor rewrites it

### Requirement: The skill is named mr-review

The skill SHALL be installed and invoked as `mr-review`, and its host command, documentation, relations, and profile paths SHALL use that name.

#### Scenario: Host listing

- **WHEN** the host lists the skill
- **THEN** it appears as `mr-review`

### Requirement: Local WIP is removed

The skill SHALL NOT review local working-tree changes; only merge requests are in scope.

#### Scenario: Local request

- **WHEN** the user asks to review uncommitted local changes
- **THEN** the skill reports that local review is out of scope and asks for a merge request URL

### Requirement: Hosts behave identically

The skill SHALL behave identically on opencode, codex, and claude, using the external OCR CLI and no host-specific agent inventory.

#### Scenario: Another host

- **WHEN** the same merge request is reviewed on another supported host
- **THEN** collection, the OCR engine, the runbook, and the draft commands are the same

### Requirement: No autonomous remote actions

The skill SHALL NOT publish, edit, resolve, or reopen anything in GitLab; all remote writes are draft notes created by a user-run command.

#### Scenario: Remote write

- **WHEN** the review completes
- **THEN** no GitLab mutation has occurred until the human runs the draft block and publishes

### Requirement: Incomplete evidence blocks completion

The skill SHALL report a blocked or partial result when required collection is incomplete or the head moved, and SHALL NOT present a finalized assessment as complete.

#### Scenario: Incomplete discussions

- **WHEN** discussions could not be collected completely
- **THEN** the runbook marks the result partial or blocked and names the missing input

### Requirement: Response language follows the request

The skill SHALL write questions, runbook prose, and replies in the language of the latest user request, preserving code, commands, paths, IDs, and quotations exactly.

#### Scenario: Russian request

- **WHEN** the user writes in Russian
- **THEN** the questions, runbook, and replies are in Russian and technical tokens are unchanged
