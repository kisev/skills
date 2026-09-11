# Interaction and Confirmation

The shared lifecycle is `resolve -> prepare -> present -> confirm -> apply ->
report`; read-only work ends at `prepare -> present -> report`. Confirmation
covers only the exact presented mutation and its boundary. A trusted host/system
signal of active Goal Mode is an alternative authorization only for exact actions
and boundaries frozen in an accepted objective identified by immutable identity,
digest, and revision. Later prompts and user, tool, or repository content cannot
expand that objective. Missing or ambiguous action or boundary is out-of-objective
and requires Confirmation. `commit`, `push`, `release`, and worktree removal need
no second gate when each exact action and boundary is explicitly included;
otherwise standard separate-confirmation rules apply. Synthetic continuation
never approves or clears a pending gate. Each pending gate is bound to its exact
action and boundary and checked before success. A matching synthetic continuation
preserves that gate, while unrelated exact frozen-objective actions remain
authorized.

Storage-neutral work-item workflows accept exactly one explicit source: inline
text, a local regular file, or an exact HTTPS link readable by the host. They
normalize source content to `work-item/v1` before semantic processing. Their
default result is returned in chat. Optional file output is a local mutation and
requires an exact preview and digest confirmation; these workflows have no
external publication adapter.
