# Errors and Status

`ok` represents a verified result; `partial` represents bounded useful output
with gaps; `blocked` represents a required decision or dependency; `error`
represents an untrustworthy operation. Errors identify cause, consequence,
missing evidence, and safe escalation.

Normalized work-item validation and review distinguish `ready`,
`needs_clarification`, and `blocked` while keeping machine and semantic findings
separate. Triage classifies evidence without issuing a quality verdict. JSON
reports and CLI exit codes are stable within the package contracts.

Code-review preparation does not execute publication commands. Direct manual
commands and the TUI report process exit and bounded redacted diagnostics, not
verified remote effects. There is no polling or persistent failure block; the user
checks GitLab and decides whether to repeat. Cancellation does not undo an accepted
request. Other profiles retain their own guarded recovery behavior.
