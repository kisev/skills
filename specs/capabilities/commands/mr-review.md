# `/mr-review`

### REQ-I-205 - Route the mr-review command

The command shall load [mr-review](../skills/mr-review.md) through the
generated adapter and pass the untrusted request through unchanged.

#### Verification

The generated adapter loads exactly `mr-review`, preserves untrusted arguments,
and performs no work of its own; the repository adapter checks cover it.
