# Errors and Status

`ok` represents a verified result; `partial` represents bounded useful output
with gaps; `blocked` represents a required decision or dependency; `error`
represents an untrustworthy operation. Errors identify cause, consequence,
missing evidence, and safe escalation.

Normalized work-item validation and review distinguish `ready`,
`needs_clarification`, and `blocked` while keeping machine and semantic findings
separate. Triage classifies evidence without issuing a quality verdict. JSON
reports and CLI exit codes are stable within the package contracts.
