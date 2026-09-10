# Interaction and Confirmation

The shared lifecycle is `resolve -> prepare -> present -> confirm -> apply ->
report`; read-only work ends at `prepare -> present -> report`. Confirmation
covers only the exact presented mutation and its boundary. External publication,
history rewrite, and destructive cleanup require separate confirmation.

Storage-neutral work-item workflows accept exactly one explicit source: inline
text, a local regular file, or an exact HTTPS link readable by the host. They
normalize source content to `work-item/v1` before semantic processing. Their
default result is returned in chat. Optional file output is a local mutation and
requires an exact preview and digest confirmation; these workflows have no
external publication adapter.
