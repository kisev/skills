# reviewmatic Test Baseline

[Русская версия](ru/reviewmatic-test-matrix.md)

`apps/reviewmatic` is the mechanical helper runtime for `mr-review`. The
TypeScript review application it replaced was removed with the runtime
reduction; no TypeScript test runner or generator remains.

## Test map

| Surface | Test file |
| - | - |
| Command surface and removed commands | `apps/reviewmatic/tests/test_cli_contract.py` |
| Read-only collection, exact refs, completeness, redaction | `apps/reviewmatic/tests/test_collect.py` |
| 8000-byte background, task priority, disclosed cuts | `apps/reviewmatic/tests/test_background.py` |
| Head check, positioned/general drafts, replies, no publish | `apps/reviewmatic/tests/test_drafts.py` |
| Snapshot freshness | `apps/reviewmatic/tests/test_revalidate.py` |
| Global/local profile overlay and no secrets | `apps/reviewmatic/tests/test_profiles.py` |
| OCR version gate, parallel runs, parsing, session compare | `apps/reviewmatic/tests/test_ocr.py` |
| Skill texts, runtime vocabulary, docs map, host parity | `apps/reviewmatic/tests/test_skill_contract.py` |
| Authored runbook fixtures (one run, two runs) | `apps/reviewmatic/tests/test_runbook_format.py` |

The materialized portable contract under `src/reviewmatic/portable/` is
checked byte-for-byte by the repository suite (`task generate:check`) and by
the portable-runtime tests in `tests/test_repository.py`.

## Fixtures

- `apps/reviewmatic/tests/fixtures/ocr/` holds the OCR review JSON and the two
  session-compare shapes; the parser is tolerant and the fixtures are inputs,
  not regenerated output.
- `apps/reviewmatic/tests/golden/` holds two authored runbook examples. They
  pin the sections the skill must produce and the ones it must not; they are
  not runtime output and are never regenerated from the implementation.

## Fake hosts

Collection tests replace the GitLab transport with recorded responses and
assert the recorded calls; draft tests run the generated shell block against a
fake `glab` on `PATH` to prove the stale-head stop and the POST count. The
package tests stay standard-library-only.

## Skill acceptance layers

The deterministic layer is the package suite above plus the repository
contract tests (`tests/test_skill_contracts.py`) that read the built
`mr-review` archive.

The live layer is user-run: `task acceptance SKILL=mr-review` drives the
`gitlab-review-live` family. It provisions a synthetic project and merge
request on the disposable local GitLab stand, checks the skill out at the exact
reviewed revisions, seeds the startup answers in the prompt, records the
runbook and draft block, moves the head to exercise `ocr session compare`, and
executes the draft block (draft notes only, never a publish) before deleting
the fixture. It needs the dev stacks, the `ocr` CLI, two configured reviewer
aliases, and provider credentials; a missing prerequisite is reported as a
skip with the exact reason. A live run stays outside `task check`,
`check:core`, the Lefthook gate, and CI.

## The acceptance umbrella

`task acceptance` (`tests/integration/acceptance.py`) drives the GitLab and
Mattermost live runs plus one minimal behavioral probe per uncovered skill.
Each probe installs only its skill into an isolated host sandbox, seeds small
fixture files, and machine-checks the produced artifact; unexercisable skills
are skipped with their reason. Every run writes `result.json` and `summary.md`
under `.build/acceptance/<timestamp>/`. The umbrella stays outside the gates;
see [the how-to](how-to/skill-acceptance.md).
