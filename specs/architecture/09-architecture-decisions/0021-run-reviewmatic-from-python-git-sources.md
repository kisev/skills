# ADR-0021: Run reviewmatic from Python Git sources

- Status: accepted
- Date: 2026-10-05
- Status changed: none
- Supersedes: [ADR-0010](0010-separate-review-and-publication.md)
- Superseded by: none

## Context and problem statement

The Python reviewmatic implementation already owns the MR and local-WIP
workflows, private artifacts, refresh/repair, and manual runbook generation. The
remaining TypeScript application and TUI create a second runtime and put a
Node/npm boundary around a Python application. The user selected Git-based
installation through `uvx` and explicitly rejected PyPI publication. The manual
runbook remains the only publication interface; the TUI is not to be rewritten.

## Decision drivers

- Keep one reviewmatic runtime and preserve MR, local-WIP, panel, repair, refresh,
  incremental, XDG, and managed-worktree behavior.
- Preserve the manual publication boundary and fail-closed head checks.
- Install the Python application from the same repository without a PyPI release
  or a persistent global tool installation.
- Keep stable and development source selection explicit.

## Considered options

- Keep the TypeScript npm runtime beside Python. Rejected because it preserves
  two application runtimes and the TUI interface the user chose to remove.
- Publish the Python application to PyPI. Rejected by the explicit user choice;
  no PyPI package or publication pipeline is introduced.
- Run the Python application from a selected Git ref with `uvx`. Accepted: the
  stable channel uses an exact release tag and the development channel uses the
  moving `dev` branch.

## Outcome

Python in `apps/reviewmatic` is the sole reviewmatic runtime. Invoke it as
`uvx --from 'git+https://github.com/kisev/skills.git@<ref>#subdirectory=apps/reviewmatic' reviewmatic`.
Use the exact matching release tag for stable skills and `dev` for development
skills. `uvx` uses an ephemeral environment; no `uv tool install`, npm runtime,
PyPI package, or in-application publication UI is required. The application
continues to write copy-ready manual `glab` runbooks and private XDG artifacts.

## Consequences

### Positive

- One runtime owns remote MR and local-WIP reviews, panels/arbitration,
  incremental decisions, targeted repair, refresh, and runbook generation.
- Existing v2 artifacts, private state, and reviewed worktrees keep their format
  and ownership; no state migration or cleanup is required.
- Stable tags and the moving development branch let users align runtime and
  skill channels without adding a registry package.
- Manual publication keeps one user-owned execution boundary.

### Negative

- Runtime acquisition depends on Git access and `uvx`; a selected moving
  development ref can be stale in the local uv cache until refreshed.
- No terminal viewer or in-app send workflow is provided. Users read and copy
  the generated runbook directly.

## Compatibility

The Python runtime retains existing artifact schemas, XDG locations, managed
worktree layout, and runbook contracts. The former `@kisev/reviewmatic` npm
package and its published versions remain untouched and are not deprecated by
this decision; a registry deprecation requires separate confirmation.

## Migration

Users select the release tag matching a stable skill or `dev` for a development
skill and invoke the app with the documented `uvx --from` Git source. Existing
artifacts remain readable without migration. A uv cache refresh affects only
runtime acquisition, not review state or runbooks.

## Rollback

Source rollback restores a prior repository revision. It does not rewrite npm
versions or tags, delete user state, or make a prior TUI available unless that
runtime is deliberately restored as a separate future decision.

## Reversibility

The Git source and `uvx` invocation can be changed in a future release without
moving existing npm versions. Restoring another runtime or adding an interface
requires a new decision and compatibility checks against retained artifacts.

## Risks

- A moving `dev` ref can be cached; the runbook documents `uvx --refresh-package reviewmatic`, while stable refs remain exact tags.
- Manual writes remain subject to uncertain outcomes and possible duplicate
  comments; runbook head checks fail closed, and users decide whether to repeat.

## Links

- Requirements: [REQ-F-105](../../capabilities/skills/code-review.md#req-f-105---review-exact-changes), [REQ-I-428](../../requirements/interfaces/README.md#req-i-428---run-reviewmatic-from-a-selected-git-ref), [REQ-F-548](../../requirements/functional/README.md#req-f-548---verify-gitlab-workflows-against-a-persistent-local-ce-server), [REQ-Q-004](../../requirements/quality/README.md#req-q-004---evidence-completeness).
- Related ADRs: [ADR-0010](0010-separate-review-and-publication.md) (superseded; manual publication boundary remains).
