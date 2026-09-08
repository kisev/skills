# Workflow

```text
python3 -I -S -B scripts/usage.py [--since ISO8601] [--project PATH] [--format json|text|both]
```

The runner reads only durable schedule state and OpenCode message storage.
Historical goal state is not treated as current runtime and does not participate
in the ledger. The runner does not create history or replace provider billing. If
cost is not available for every accounted turn, `cost` remains `null` and
`cost_status` is `unknown`; unknown is never converted to zero. A corrupted
component produces a partial report with an error without concealing data from
other components.
