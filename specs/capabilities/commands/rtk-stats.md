# `/rtk-stats`

### REQ-I-234 - Route the rtk-stats command

The command shall render the RTK compression observability summary from
`doctor --json` (`rtk.observability` check) without loading a skill and without
mutating state.

#### Verification

Generated adapter tests verify the exact template rendering and untrusted
arguments.
