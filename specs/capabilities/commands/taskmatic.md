# Command `taskmatic`

### REQ-I-408 - Route the taskmatic command

The command shall select the [taskmatic skill](../skills/taskmatic.md) through
[REQ-I-002](../../requirements/interfaces/README.md#req-i-002---command-interface),
without adding a second store or web server to the adapter.

#### Verification

Rendered command tests verify native skill loading and the missing-skill
installation message; taskmatic runtime tests own board behavior.
