# Errors and Status

`ok` represents a verified result; `partial` represents bounded useful output
with gaps; `blocked` represents a required decision or dependency; `error`
represents an untrustworthy operation. Errors identify cause, consequence,
missing evidence, and safe escalation.

Normalized work-item validation and review distinguish `ready`,
`needs_clarification`, and `blocked` while keeping machine and semantic findings
separate. Triage classifies evidence without issuing a quality verdict. JSON
reports and CLI exit codes are stable within the package contracts.

For code-review publication, a definitive non-mutating HTTP rejection is
`blocked` with bounded redacted method, endpoint, exit-code, status, and response
diagnostics plus retry evidence. Timeout, 5xx, malformed response, failed
postcondition observation, and any unknown mutation outcome are `partial`; they
record uncertainty and never trigger automatic replay. Progress is written to
stderr and the final status remains structured JSON on stdout.
