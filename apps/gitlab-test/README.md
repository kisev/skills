# Local GitLab workflow tests

[Русский](README.ru.md)

This opt-in environment uses GitLab CE `18.11.11-ce.0`, GitLab Runner `v18.11.0`
and the repository's `glab 1.120.0`. Runner executes shell jobs inside its own
container, with no host Docker socket. Docker executor and paid EE features are
outside scope. Ordinary `task check` needs no running server.

## Run

Prerequisites: Linux, Docker Engine, Compose v2, OpenSSL, Git, the Mise toolchain
and a working Chromium installation. Allow several minutes for GitLab startup
and enough memory for GitLab plus the browser. Reset testing starts a second
GitLab instance. Images and the browser are downloaded when needed.

```sh
mise install
mise exec -- agent-browser install
task generate
task gitlab:config
task gitlab:test
```

Repeat `task gitlab:test`; no signup, token entry or fixture preparation is
required. Tasks default to `docker-compose`. Set `COMPOSE="docker compose"` when
using the CLI plugin. `GL_TEST_PROJECT` selects the Compose project (default
`gitlab-workflows`); `GL_TEST_PORT` selects the loopback HTTPS port (default
`443`). Keep these values for subsequent commands. Images are not overridable.
Use the default port for full workflow checks: `glab 1.120.0` rejects a port in
`--hostname`. Nonstandard ports support API/lifecycle checks only; the disposable
reset test uses one and does not run the collectors.

`config` validates without starting containers. `up` starts them. `init` also
reconciles owned accounts and projects and prints the free-zone URL. `logs` shows
logs after an ownership check. `down` stops containers and retains volumes.
Every task goes through the same checkout-bound ownership driver.

HTTPS is published only on `127.0.0.1`. Use `localhost` in URLs: its certificate
is signed by the stand's separate CA. Tests verify that CA; Chromium pins the
verified leaf key in an isolated session. No system trust store is changed.
GitLab and Runner communicate over the internal Compose network. Only the
synthetic fixture repositories are mutated. The free project is not rewritten
by ordinary tests. Do not put production data into this stand.

## Evidence and limits

Ignored state lives in `.build/gitlab-test/<project>/state/`, with private
credentials and isolated Git/glab/XDG directories. Reports live separately in
`reports/<run>/result.json`; `reports/latest.json` points to the last operation.
Reports retain failures, versions, startup duration, container resource samples,
API observations, traces and browser screenshots. Failures and timeouts return
nonzero. Preparation is checked separately from authorized synthetic writes.
`browser-network.json` retains XHR/fetch URLs, methods, statuses and transport
errors without request headers, cookies or bodies, including on a failed UI check.

| Scenario | Expected result | Server postcondition |
| - | - | - |
| Accounts and reruns | Owned identities reused | Authenticated IDs, stable project IDs |
| Pagination | Real glab follows multiple pages | All three run-specific issues present with `per_page=1` |
| Issue metadata and links | CE accepts labels, milestones, `relates_to` | GET issues and links returns exact metadata and target |
| Tags and releases | Release identifies fixture commit | GET release returns the exact SHA |
| Shell CI | Success, allowed failure, child job execute | Exact-SHA terminal pipeline, real job states and trace markers |
| Inline comments | Old/new/context positions accepted | Returned position and head SHA match requested payload |
| Suggestions | Server recognizes a suggestion | Nonempty server suggestion metadata; browser application checks resulting file |
| Replies and threads | Author reply; separate resolve/reopen | Author ID and resolved flag read back after each operation |
| Negative API | Outsider and invalid line rejected | Expected non-2xx status, never a successful write |
| MR/release preparation | Collect complete exact-head evidence without publication | Discussions unchanged, incomplete helper evidence rejected |
| MR publication | Copy the generated commands, as reviewer and author | Exact literal title/description/labels; human discussion notes unchanged |
| Task publication | Execute the copied marker-wrapped GraphQL command | Real issue title, labels and milestone match the plan |
| Task preparation/triage | Local plan and actual collection | Issue catalog unchanged during preparation |
| Reviewmatic | Prepare, presentation-repair, then copy runbook commands | Findings, suggestions and fixture receipts retained; real grouped suggestions and replies published |
| CI-only refresh | Rerun real shell CI on the same SHA, then finish the existing draft | Supplemental CI snapshot; original findings/evidence/receipts retained; no repeated `startReview` |
| Material refresh | Collect changed conversations without publishing or rebinding receipts | Findings/dispositions and original draft preserved; new receipts empty; last finalized plan remains readable |
| TUI | Real Ink CLI in a PTY; cancel confirmation, then confirm a reply | No early write; exactly one reviewer reply; thread state unchanged; transcript retained |
| Browser | Single and cross-file grouped suggestions apply | Screenshots, exact files and partial/full application flags; partial is not a complete fix |
| Transport fault/retry | Inject CLI failure, then retry the actual collector | Failure is nonzero; retry has complete evidence; server unchanged |
| Free zone | Ordinary checks and down/up leave fingerprinted data alone | All branch/tag trees, issue/MR discussions, metadata, wiki content and local `free/` fingerprints unchanged |
| Reset | Selected stand only, reports retained | New disposable identity; primary free project unchanged |

The harness does **not** yet prove the complete acceptance matrix. Missing cases
include exhaustive helper pagination/roles for all six workflows, reviewmatic's
old/new/context and single-suggestion commands, TUI issue and separate thread-state
actions, same-file grouped stale-state recovery, task
triage publication, full release inventory/readiness/publication and in-flight
mutation cancellation/retry. Free-zone upload/snippet payloads and arbitrary data
outside the fingerprinted local `free/` directory are not verified. Only metadata
is fingerprinted for uploads/snippets; reports contain hashes, not free-zone prose.
Deterministic receipt inputs are not real critic runs.
Do not interpret baseline API checks or offline suites as those missing proofs.
Until that mandatory coverage is implemented, `test` records the missing cases
and returns nonzero even when every available baseline scenario passes.
Reports include UTC `started_at`, per-scenario pass/fail/not-run and durations,
plus initial/final resource samples. `test` performs a retaining down/up after
browser checks. A transport fault wrapper is explicitly marked as injection;
it is never used as evidence of a GitLab network response.

## Reset

```sh
task gitlab:reset
GL_RESET_CONFIRM=the_printed_digest task gitlab:reset
task gitlab:test-reset
```

The first command prints the exact container, volume and state scope without
deleting anything. Confirmation binds that scope; a changed scope fails closed.
Reset removes only the selected stand's volumes and private state, including its
free project and credentials, retains reports and initializes again. Symlinks,
foreign checkout resources and unexpected volumes are rejected. The reset test
uses a separate random project and the adjacent port; its data remain available
for inspection, with containers stopped after a successful test.

## Optional live

```sh
EVAL_HOST=opencode EVAL_MODEL=provider/model EVAL_TIMEOUT=300 \
  EVAL_MAX_TOKENS=12000 EVAL_MAX_COST=1 task gitlab:live
```

Use actual values and explicitly supplied provider credentials/configuration.
Existing `opencode`/`codex` host adapters are reused. Global host credentials are
not copied. Live checks the MR-preparation artifact and the manual publication
boundary, not just the agent's claim. This is not a live assessment of all six
workflows. Missing settings, credentials or token/cost telemetry fail closed.
Timeout bounds execution; returned telemetry checks budgets after execution,
not as a prepaid cost ceiling. Live is optional and requires no CI job.

On failure, retain state, inspect the report and `task gitlab:logs`, fix the cause
and repeat. Never reset persistent data merely to obtain a green test.
