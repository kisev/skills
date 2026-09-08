```text
python3 -I -S -B scripts/overview.py [--project PATH] [--all] [--format json|text|both]
```

The runner reads only documented file-backed schedule and attempts state. Historical goal state is intentionally not considered active runtime and is not included in the current overview. `--all` uses only explicit `projects.json`; it does not scan disk. Corrupt, missing, and unsupported records are identified at component level; the runner does not start sessions, plugins, network, or recovery.

# Overview

```text
python3 -I -S -B scripts/overview.py [--project PATH] [--all] [--format json|text|both]
```

The runner reads only documented file-backed schedule and attempts state. Historical goal state is intentionally not considered active runtime and is not included in the current summary. `--all` uses only explicit `projects.json`; it does not scan the disk. Corrupt, missing, and unsupported records are marked at component level; the runner does not start sessions, plugins, network activity, or recovery.
