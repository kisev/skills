# Workflow

Definitions are located either in `.agents/loops/*.md` or in user-owned XDG state.
Every new managed definition is always `enabled: false`. The scheduler exists only
when the plugin is explicitly enabled and does not replay missed slots after a
restart.

```text
python3 -I -S -B scripts/schedule.py list|status [--project PATH]
python3 -I -S -B scripts/schedule.py add --id ID --name NAME --schedule 'every: 1h' \
  --agent AGENT --model MODEL --prompt TEXT
python3 -I -S -B scripts/schedule.py enable|disable|remove --id ID
```

Each mutating operation first returns an exact preview and a one-time
`confirmation_request`. Apply verifies the digest and revision. The runner does
not start sessions, create timers, or change a definition without confirmation.
