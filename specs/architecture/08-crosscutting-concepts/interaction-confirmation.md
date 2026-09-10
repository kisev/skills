# Interaction and Confirmation

The shared lifecycle is `resolve -> prepare -> present -> confirm -> apply ->
report`; read-only work ends at `prepare -> present -> report`. Confirmation
covers only the exact presented mutation and its boundary. External publication,
history rewrite, and destructive cleanup require separate confirmation.
