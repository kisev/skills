# `/mattermost-triage`

### REQ-I-404 - Route the mattermost-triage command

The command shall load [mattermost-triage](../skills/mattermost-triage.md) through
the [shared command interface](../../requirements/interfaces/README.md#req-i-002---command-interface).
The skill owns selection, incremental state, analysis, artifacts, and prepared
response actions.

#### Verification

The generated adapter loads exactly `mattermost-triage`, preserves untrusted
arguments, and contains no independent triage, state, or mutation protocol.
