# `/code-review`

### REQ-I-205 - Route the code-review command

The command shall load [code-review](../skills/code-review.md) through the
[shared command interface](../../requirements/interfaces/README.md#req-i-002---command-interface).
The skill owns target selection, runner invocation, review, and publication plans.

#### Verification

The generated adapter loads exactly `code-review`, preserves untrusted arguments,
and contains no independent review, state, or publication logic.
