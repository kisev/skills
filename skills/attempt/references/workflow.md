# Attempt

`background_attempts` is the sole owner of the queue, dispatch, child session, worktree, and durable state. The skill does not create its own lifecycle and does not select an agent or model.

Valid statuses are `queued`, `running`, `waiting`, `completed`, `failed`, `cancelled`, and `orphaned`. Only the final four statuses are terminal. `list` reads the summary of the current parent session/project, `status` shows the exact record, and `result` reads a structured result only after a terminal transition.

Before cancelling, read status and show `attempt_id`, revision, status, child session, and workspace. Request a native Question, then pass the exact `attempt_id`, `expected_revision`, and `expected_status`. A terminal attempt returns a no-op; a stale revision/status, user rejection, and an unconfirmed abort do not delete state, transcript, evidence, or workspace.
