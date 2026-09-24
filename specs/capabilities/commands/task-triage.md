# `/task-triage`

### REQ-I-225 - Route the task-triage command

The command shall load [task-triage](../skills/task-triage.md) through the
[shared command interface](../../requirements/interfaces/README.md#req-i-002---command-interface).
The skill owns collection, analysis, release planning, artifacts, and publication.

#### Verification

The generated adapter loads exactly `task-triage`, preserves untrusted arguments,
and contains no independent triage or mutation protocol.
