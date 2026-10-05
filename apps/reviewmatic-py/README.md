# reviewmatic (Python port)

[Русская версия](README.ru.md)

Python implementation of the reviewmatic GitLab review CLI. Stage 1 of the
port ships the package skeleton, the complete command surface of the
TypeScript CLI (`apps/reviewmatic`), and the canonical contract core — no
review business logic yet.

## Install and run

The package is built and run from this repository with uv:

```shell
uv run --locked reviewmatic --version
uv run --locked reviewmatic --help
uv build
```

The PyPI name `reviewmatic` is reserved for this package; publication happens
in a later stage.

## Scope

Stage 1 implements the contract operations that the canonical runtime fully
provides: `capabilities`, `assess-mode`, the historical `publication` stub,
and `marker-run`. Every other subcommand parses its arguments exactly like the
TypeScript CLI and answers an explicit not-implemented envelope with exit
code 5; the business logic lands in stage 2.

Exit codes follow the TypeScript contract: `0` success, `1` unexpected
failure, `2` invalid input or blocked, `3` tool unavailable, `4` unsupported
mode, `5` not implemented in stage 1.

## Canonical contract core

`src/reviewmatic/portable/` is materialized byte-for-byte from the canonical
sources in `shared/references/` (`shared/manifest.json`, section
`pythonRuntime`). Never edit those files: change the canon, then run
`task generate` and verify with `task generate:check`.

Digest parity with the TypeScript implementation is enforced by committed
golden fixtures under `tests/golden/`. They are generated from the real
TypeScript sources with `task reviewmatic-py:fixtures` and byte-checked in
`task generate:check`; the Python parity tests fail on any divergence.

## validateV2Artifact strictness

The Python validator `validate_v2_artifact` is the strictness reference for
the port. Timestamp validation is canonical and strict: the extended ISO-8601
format with calendar, time-range, and offset checks
(`_iso_format_is_valid`). This is an intentional fix relative to Python
history: timestamps used to go through `datetime.fromisoformat`, which also
accepts compact basic formats (`20261005T000000`); TypeScript rejects that
input and Python now rejects it too. The divergence was bounded to exactly
this class: the probe at
`apps/reviewmatic/scripts/probe-v2-divergence.mjs` runs identical artifacts
through both validators (envelope, timestamps, component snapshots,
local-review reports, context packages), and the verdicts agree on every case.

## Development

```shell
uv run --locked pytest
uv run --locked mypy
uv run --locked ruff check .
```

The application-local `pyproject.toml` mirrors the repository lint selection
and carries the per-file ignores of the materialized canonical modules.
