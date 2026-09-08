# Selective RTK use

RTK is an external CLI and is not installed by this skill. Check availability from the skill directory with `python3 -I -S -B scripts/rtk.py check`. If unavailable, the runner returns JSON `escalate`; do not install the tool automatically.

Use RTK for an initial overview of large, repetitive, and primarily informational output: full tests, builds, linters, Git summaries, and logs. Its compact output may be filtered, deduplicated, truncated, summarized, or reordered. Its absence of data is not evidence of absence.

Always run the original command directly when full, exact, ordered, or machine-readable output is needed, including code review, diagnostics, security checking, deployment, writing, deletion, migration, and proof of the absence of an object or error.

## Workflow

1. For a noisy operation, use RTK as a broad first pass.
2. Identify a concrete test, file, error, resource, or time range.
3. Run a narrow original command for a decision or exact evidence.
4. Do not add a hook that automatically substitutes commands without a separate request.

Examples:

```shell
rtk pytest tests/
pytest tests/test_contract.py -vv

rtk git status
git diff -- path/to/file
```

Before using an unfamiliar wrapper, read `rtk --help` or `rtk <command> --help`. Detailed category boundaries are in `references/per-tool.md`.
