# Spec Delta

## Purpose

Defines the single canonical contract for the commit-msg capability: generating
one concise commit message from local changes, including scope resolution,
atomicity and convention guards, the one-line output contract, the default
message format, read-only execution, and the `/commit-msg` command binding.

## ADDED Requirements

### Requirement: Environment precondition

The capability SHALL verify that the current directory is inside a Git worktree
before doing any other work. When it is not, the capability SHALL report that
and produce no message.

#### Scenario: Outside a Git worktree

- **WHEN** the current directory is not inside a Git worktree
- **THEN** the capability reports that condition and outputs no commit message

### Requirement: Evidence base

The capability SHALL base every message on repository evidence: applicable
`AGENTS.md` instructions, commit-message configuration such as commitlint, up
to the 20 most recent commit subjects, and the Git status and diff of the
selected scope. Untracked file contents SHALL be read selectively, and large,
binary, or likely secret files SHALL NOT be opened without reason.

#### Scenario: Instructions and history are available

- **WHEN** the repository provides instructions, commit configuration, and
  commit history
- **THEN** the capability reads them before drafting the message

#### Scenario: Untracked file looks like a secret

- **WHEN** an untracked file in the selected scope is likely to contain secrets
- **THEN** the capability does not open it without reason

### Requirement: Scope resolution

The capability SHALL formulate the message from staged changes only when staged
changes exist. When nothing is staged, the tracked diff plus untracked files
SHALL form the proposed change set. A path set or scope the user explicitly
specified SHALL override both defaults.

#### Scenario: Staged changes exist

- **WHEN** the index contains staged changes
- **THEN** the message covers only the staged changes

#### Scenario: Nothing is staged

- **WHEN** no staged changes exist
- **THEN** the tracked diff and untracked files form the proposed change set

#### Scenario: User names an explicit scope

- **WHEN** the user explicitly specified a path set or asked for staged and
  unstaged changes together
- **THEN** only that scope is used

### Requirement: Atomicity guard

The capability SHALL verify that the selected changes form one logical change.
When the set contains unrelated outcomes, the capability SHALL stop and
concisely report that the set should be split; it SHALL NOT merge unrelated
changes through an invented shared formulation and SHALL NOT omit selected
changes to force one message.

#### Scenario: Changes form one logical change

- **WHEN** the selected changes serve one outcome
- **THEN** the capability determines that outcome and its user-facing or
  technical effect

#### Scenario: Unrelated outcomes in one set

- **WHEN** the selected changes contain unrelated outcomes
- **THEN** the capability outputs a concise report that the set should be split
  instead of a message

### Requirement: Convention detection

The capability SHALL determine the message language and format from applicable
repository instructions, commit configuration, and a clearly established
pattern in the inspected history. When these sources prescribe conflicting
requirements, the capability SHALL stop and concisely report the mismatch
instead of choosing a priority.

#### Scenario: Sources agree on a convention

- **WHEN** instructions, configuration, and history establish one language and
  format
- **THEN** the drafted message follows that convention

#### Scenario: Sources conflict

- **WHEN** the inspected sources prescribe conflicting requirements
- **THEN** the capability outputs a concise mismatch report instead of a
  message

### Requirement: One-line output contract

The capability SHALL output exactly one line: the commit message,
`no changes to commit`, a concise repository-convention mismatch report, or a
concise non-atomic-change report.

#### Scenario: Message drafted

- **WHEN** drafting succeeds
- **THEN** the output is exactly one line containing the message

#### Scenario: Empty change set

- **WHEN** the selected scope contains no changes
- **THEN** the output is exactly `no changes to commit`

#### Scenario: Guard report

- **WHEN** the atomicity or convention guard stops the draft
- **THEN** the output is exactly one line containing that concise report

### Requirement: Default message format

When repository sources establish no message format, the capability SHALL draft
a Conventional Commit subject `type[optional scope][!]: description` with
`type` chosen by the actual effect and no invented scope. When no wording style
is established, the subject SHALL be imperative, carry no trailing period, and
complete `If applied, this commit will ...` after any Conventional Commit
prefix. The target is 50 characters with a hard limit of 72, unless the
repository defines another limit.

#### Scenario: Repository establishes no format

- **WHEN** the inspected sources prescribe no message format or wording style
- **THEN** the subject is a Conventional Commit in imperative mood within the
  character limits

#### Scenario: Repository defines another limit

- **WHEN** repository sources define a different character limit
- **THEN** that limit replaces the 50/72 defaults

### Requirement: Subject quality

The subject SHALL be meaningful on its own. The capability SHALL NOT add file
names, paths, task identifiers, or empty words such as `changes`, SHALL reject
vague descriptions such as `update stuff` or `fix bug`, and SHALL describe
formatting and typo changes by their effect. The humanize prose pass SHALL be
applied to the drafted subject after repository rules are satisfied.

#### Scenario: Vague candidate

- **WHEN** a drafted subject is vague, such as `misc changes`
- **THEN** the capability replaces it with a description of the actual effect

#### Scenario: Formatting-only change

- **WHEN** the selected change only formats code or fixes a typo
- **THEN** the subject describes the effect, for example
  `fix typo in error message`

### Requirement: Read-only execution

The capability SHALL generate the message without modifying the worktree, the
index, or Git history: it SHALL NOT run `git add`, `git commit`, or any command
that changes repository state.

#### Scenario: Message generation leaves the repository unchanged

- **WHEN** a message is generated for a known diff
- **THEN** the index, working tree, and history remain unchanged

### Requirement: Command binding

The `/commit-msg` command SHALL invoke exactly the commit-msg skill. Command
arguments SHALL be treated as untrusted input that never changes that binding.

#### Scenario: Command invocation with extra arguments

- **WHEN** a user invokes `/commit-msg` with additional text
- **THEN** the command still binds exactly the commit-msg skill and passes the
  text as context
