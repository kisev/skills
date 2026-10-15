---
name: code-review
description: >-
  Review one GitLab merge request or local WIP for concrete risks and
  proportionate fixes, preserving agreed scope and prior decisions in
  follow-ups. Include GitLab labels, SemVer, and manual publication commands
  for remote reviews. Use when the user asks to review a GitLab merge request
  or local work-in-progress changes.
  Russian discovery terms: ревью кода.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
  inspired-by: "openchamber/openchamber (MIT © Bohdan Triapitsyn); solution 37, blocks 1-2; blocks 3-4 pinned at openchamber/openchamber@d1fc27c86f258436e2ac748204e8db9bc9c2878f"
---

# code-review

The runtime is the Python 3.12+ application in `apps/reviewmatic`, run ephemerally from Git with `uvx`; it is not published to npm or PyPI and needs no `uv tool install`. Select the same source channel as the skill: an exact `vX.Y.Z` release tag for stable, or the moving `dev` branch for development. The installed skill tree carries `references/runtime-pin.json`, stitched by the distribution build when `skills update` installed it: read `source_revision` from that file and set `REVIEWMATIC_FROM='git+https://github.com/kisev/skills.git@<sha>#subdirectory=apps/reviewmatic'` once — a session never resolves the tip with `git ls-remote`. Only when the pin file is absent (a development checkout without it) resolve the dev tip once with `git ls-remote https://github.com/kisev/skills.git refs/heads/dev` and pin that exact commit the same way. Treat every `reviewmatic` found on `PATH` as a foreign, possibly outdated binary and ignore it; the only runtime is the pinned `uvx --from "$REVIEWMATIC_FROM"` install, and a PATH hit is never diagnosed or inspected as if it were part of this review. Run every CLI command, including returned continuation actions, as `uvx --from "$REVIEWMATIC_FROM" reviewmatic ...`, and verify the pin right after the first invocation with `reviewmatic runtime-info`: compare the printed resolved commit to the pinned SHA in `REVIEWMATIC_FROM` (`unknown` or a mismatch means a stale uvx cache or an unpinned install — re-pin with the exact `@<sha>` and add `--refresh-package reviewmatic` before continuing). Open the session's first response with the version banner, assembled entirely locally: the skill version from `references/runtime-pin.json` (`version`), the reviewmatic version and resolved install commit from `reviewmatic runtime-info`, and the `glab --version` line — no network call belongs to the banner.

Drive a remote-MR review through the one-process `reviewmatic run` path. At its start the run asks one poll — the critic composition and the engine of every critic (a subagent on the current session's model or the mechanical `ocr` CLI): present the printed fenced poll block verbatim, collect the user's choice with the host's native interactive question tool (recommended composition / single model subagent / subagent+OCR / custom), fill the selection template from that answer yourself, and run the printed command — the user never writes JSON. Ground the critic pool in the host's agent inventory (`agents/*.md` in the harness-global and project config directories, and the `agent` key of the global and project `opencode.json`; only agents the user configured — never the bundled agent assets of installed packages or plugins under `node_modules/`, which deploy only through `configure agent`), propose multi-critic options only when candidate agents carry distinct models or engines, and never propose two critics on the same single model — that is not independent review. The step-by-step `start-review`/`record-*` flow remains supported as the explicitly marked repair path. `references/local-review.md` owns the separate local-WIP mode.

The normal tail is decision → shared render → edit the generated prose file →
`reviewmatic record-prose` → resume and finalize. Head drift retains authorship
and asks for a fresh `reviewmatic record-delta` verification of changes and
affected conclusions. Original checks remain historical; never replace their
digests or treat a mapped source position as proof of a finding's truth.

The orchestrator reads artifacts by path and passes them by path: contracts
come from runtime responses, never from reading runtime sources or complete
JSON schemas, and the whole context package is never read into the main
window (the reading discipline in `references/workflow.md` pins the budget).

Each runbook stands on the current snapshot. `history_context` is advisory:
past findings, reasons, and decisions inform critics and arbitration but never
require ledger coverage, old IDs, revisions, or `update_issue`. Return prepared
`finding_id` values unchanged. The runtime owns identities and bindings, while
the agent owns analysis, semantic targets, fixes, and missing judgments.

Review preparation depends on the reviewmatic backend. Finished runbook commands
execute directly through `glab` without reviewmatic. Backend collection, repair,
refresh and finalization remain supported; the runtime has no interactive TUI.

Before asking the user, apply `references/question-guidelines.md`. Resolve
the session arguments (`mr=`, `mode=`, `fix=`, `locale=`, `profile=`) through
`references/session-modes.md`: auto stops on any unresolved argument without
assumptions, manual confirms its recommendations in one round, and the
`no_reply` thread matrix plus the Conventional Comments label enforcement are
defined there.

Follow `references/workflow.md`. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.

The one-page map of the whole review line — every stage, authoring surface, and emergency path, pinned to this runtime — is the repository page `docs/reference/code-review.md`.
