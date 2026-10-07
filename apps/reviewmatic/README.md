# reviewmatic

[Русская версия](README.ru.md)

`reviewmatic` is the Python runtime for the `code-review` skill. It prepares
GitLab merge-request reviews and local WIP reviews, maintains private XDG
artifacts, and writes copy-ready manual `glab` runbooks. It does not publish
changes or provide a terminal UI.

## Run from Git with uvx

Use the same source channel as the installed skill. Stable skills use an exact
release tag (`vX.Y.Z`); development skills use the moving `dev` branch. Set the
ref to the actual tag or branch before running the command:

```shell
REVIEWMATIC_REF='<ref>'
uvx --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic" reviewmatic --version
uvx --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic" reviewmatic --help
```

For development builds, set `REVIEWMATIC_REF=dev`. Use `uvx --refresh-package
reviewmatic --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic"
reviewmatic --version` to refresh cached source and build data. `uvx` creates an
ephemeral tool environment; no `uv tool install` or PyPI publication is
required. Git and `glab` are external runtime tools.

The uv cache stores the executable, not review artifacts. Clearing the cache
does not remove drafts or `runbook.md` under the configured XDG state directory.
After `uv cache clean`, invoke the selected ref again:

```shell
uvx --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic" reviewmatic --version
```

This rebuilds the runtime but keeps the XDG state. To regenerate a runbook after
a repair, run `repair-review` through that same `uvx --from` source, then run
the returned `finish-review` continuation through the same source.

## Review the current snapshot

Use `reviewmatic run --url <mr-url> --repo-root <checkout>` and follow its printed
commands. After the recorded decision, fill missing prose and semantic choices
in the returned file, apply it with `record-prose`, and resume the same run.
Keep prepared `finding_id` values unchanged. Positions, suggestion ranges,
bindings, patch digests, and revisions belong to the runtime. Ordinary multiline
fixes use an exact source target and replacement text, without structural repair.

Each runbook stands on the current snapshot. Previous findings, reasons, and
decisions are advisory `history_context`, with snapshot bindings and warnings.
They do not require old IDs, issue carryover, revision inheritance, `update_issue`,
or ledger synchronization. An eligible prior snapshot still enables delta
analysis, including OCR. An unusable baseline selects full analysis with a reason.
Incomplete current evidence remains blocking.

The runtime prepares the SemVer basis from catalog and local Git evidence. To
select a policy-specific publication, use `semver_assessment.basis: {name,source}`
from the collected catalog, never a SHA. Fill the substantive policy and impact
assessments. Label rows contain `{name,status,rationale}` for the whole catalog.
Rejected candidates retain their recorded reason and binding.

Resume keeps filled prose. CI-only drift asks for CI assessment, changed
conversations require substantive checks, and head drift requires delta and
affected-conclusion verification. Old receipts retain their original digests.
Ambiguous targets and unverified current evidence request addressed correction.
Publication commands remain manual. Offline tests do not establish a live tail
duration of at most 15 minutes.

## Development and build

```shell
task reviewmatic:check
task reviewmatic:install-smoke
uv build
```

The wheel and source distribution are standard Python artifacts. Runtime
dependencies are empty; Python 3.12+ is required. The install smoke builds a
local Git snapshot, wheel, and source distribution outside the checkout, then
runs them with isolated `uvx` environments without Node, `PYTHONPATH`, or a
persistent `reviewmatic` installation.

## Canonical portable runtime

`src/reviewmatic/portable/` is materialized byte-for-byte from
`shared/references/` through `shared/manifest.json` (`pythonRuntime`). Edit the
shared source, then run `task generate` and `task generate:check`. Do not edit
the materialized copy directly.

The 33 committed golden fixtures preserve the contract expectations generated
from TypeScript revision
`3e409c217e94d643f77eb543caab9a2ed4b7288d`. The former TypeScript application
and generator have been removed. `test_golden_parity.py` recomputes every digest,
verdict, and transition output against those frozen expectations; it does not
regenerate fixtures from Python or skip assertions. See
[`docs/reviewmatic-test-matrix.md`](../../docs/reviewmatic-test-matrix.md) for
the source test baseline and port mapping.

## validateV2Artifact strictness

The Python validator `validate_v2_artifact` is the strictness reference for the
port. Timestamp validation is canonical and strict: the extended ISO-8601
format with calendar, time-range, and offset checks (`_iso_format_is_valid`).
This is an intentional fix relative to Python history: timestamps used to go
through `datetime.fromisoformat`, which also accepts compact basic formats
(`20261005T000000`); TypeScript rejected that input, and Python now rejects it
too. The divergence was bounded to exactly this class; the committed golden
fixtures lock the validator verdicts, so any drift from the TypeScript
strictness fails the parity tests.
