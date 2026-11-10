# reviewmatic

[Русская версия](README.ru.md)

`reviewmatic` is the mechanical helper runtime for the `mr-review` skill. It
collects one GitLab merge request read-only, assembles the bounded OCR
background, runs the OpenCodeReview engine, compares sessions, revalidates the
head, loads review profiles, and generates GitLab draft-note commands. It never
reviews content and never mutates GitLab.

## Commands

- `collect` — read-only exact collection with completeness and redaction.
- `background` — the 8000-byte background, task first, with disclosed cuts.
- `ocr-runs` — one OCR process per reviewer alias, in parallel.
- `ocr-compare` — new, persisting, resolved, and not-reviewed groups.
- `revalidate` — head freshness against a collected snapshot.
- `profiles` — the effective profile and provider validation.
- `drafts` — the head check and the GitLab draft-note shell block.
- `runtime-info` — the version and the resolved install commit.

## Run from Git with uvx

Use the same source channel as the installed skill. Stable skills use an exact
release tag (`vX.Y.Z`); development skills use the moving `dev` branch:

```shell
REVIEWMATIC_REF='<ref>'
uvx --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic" reviewmatic runtime-info
```

`uvx` creates an ephemeral tool environment; no `uv tool install` or PyPI
publication is required. Refresh cached source with `--refresh-package reviewmatic`
when the selected ref moved. `uv cache clean` removes the executable but not
drafts or `runbook.md` under the private state directory.
`git`, `glab`, and the external `ocr` CLI (minimum 1.13.6) are external runtime
dependencies.

## Profiles

Reviewer aliases live in `~/.reviewmatic/reviewers.json` and
`./.reviewmatic/reviewers.json`; the local file overlays the global one by
alias and default. A profile holds `alias`, `provider`, `model`, and `effort`,
never secrets.
