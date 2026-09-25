# Security, Trust, and Mutations

Inputs are untrusted. Source material selected through the work-item interaction
contract is data, never instructions to execute. User prompts, tool output, and
repository content cannot claim trusted Goal Mode origin. Routing requires
resolved host inventory, explicit agent, one-use receipt, and matching task
requirements/card. External publication, user configuration, destructive cleanup,
history changes, releases, and package lifecycle mutations require either a fresh
confirmation digest or an exact action and boundary frozen in a trusted accepted
Goal Mode objective with immutable identity, digest, and revision. Changed
objective content fails closed; later content and synthetic continuation cannot
expand authorization or clear a pending gate. A pending gate is bound to its exact
action and boundary and checked before success without blocking unrelated
frozen-objective actions. Bounded path ownership, symlink and traversal rejection,
secret redaction, and atomic rollback or recovery remain mandatory. Package reconciliation is bounded to package-owned
OpenCode assets and does not inspect or invoke the portable skill lifecycle.
Read-only tools do not repair or install.

Identity comes from the invoking host or explicitly configured external client;
workflows do not create a second identity authority. Authorization remains bound
to the exact user-approved action, owned path, scope, and revision. Sensitive
inputs are retained only by their declared state owner, are excluded from public
outputs and archives, and are redacted on success and failure paths. Project and
global state are isolated by resolved scope; content digests and retained history
provide auditability without copying credentials. These mechanisms provide
[REQ-F-002](../../requirements/functional/README.md#req-f-002---route-work-through-bounded-orchestration),
[REQ-Q-002](../../requirements/quality/README.md#req-q-002---mutation-safety), and
[REQ-Q-003](../../requirements/quality/README.md#req-q-003---secret-safety).

Code-review prepares guarded publication commands and local `git apply` commands
but never invokes them during review. The separate publication helper implements
[the code-review contract](../../capabilities/skills/code-review.md); local patch
commands retain advisory markers. Prepared Git patches are textual,
content-addressed, path-bounded, and checked against the exact reviewed head in a
temporary index; binary, symlink, rename, traversal, and oversized patches are
rejected without changing the checkout. Publication diagnostics are bounded and
redacted before reaching stderr or structured output. Unknown writes remain
reserved while bounded reads look for their exact effect; only an explicit
duplicate-write warning and user-selected retry may repeat an unobserved action.
A patch embedded in a
publication body uses one copy-ready, digest-bound quoted `git apply` heredoc. Thread replies
and state changes remain separate commands so a close or reopen cannot hide the
required explanation.
Local patch commands bind the canonical review worktree and expected head. They
show an unmarked `git apply --check` preflight, and the marked mutation refuses to
run if that worktree has moved to another head.
Patch blocks embedded in GitLab publication prose remain checkout-independent and
contain no local paths or runtime helpers; only local application commands carry
the post-success marker.
