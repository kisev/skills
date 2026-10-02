# Local GitLab workflow tests

[Русский](README.ru.md)

These tests use the shared [development environment](../../../dev/README.md):
GitLab CE `18.11.11-ce.0`, GitLab Runner `v18.11.0`
and the repository's `glab 1.120.0`. Runner executes shell jobs inside its own
container, with no host Docker socket. Docker executor and paid EE features are
outside scope. Ordinary `task check` needs no running server.

## Run

Prerequisites: Linux, Docker Engine, Compose v2, OpenSSL, Git, the Mise toolchain
and a working Chromium installation. Allow several minutes for GitLab startup
and enough memory for GitLab plus the browser. Provision the pinned images and
browser before running the tests.
Preflight stops with diagnostics if they are missing; it never substitutes versions.

```sh
mise install
mise exec -- agent-browser install
task generate
task env:gitlab:up
task test:integration:gitlab:preflight
task test:integration:gitlab
```

Repeat `task test:integration:gitlab` against the already running service. Tests
do not start/stop containers or initialize accounts; `env:gitlab:up` prepares them.
Tasks default to `docker-compose`; set `COMPOSE="docker compose"` for the CLI plugin.
`GL_TEST_PORT` selects the loopback HTTPS port (default `443`). Keep it for subsequent
commands. There is one `skills-dev` Compose project; images are not overridable.
Use the default port for full workflow checks: `glab 1.120.0` rejects a port in
`--hostname`. Nonstandard ports support API/lifecycle checks only.
`env:gitlab:up` prints the manual-group URL; lifecycle commands and cleanup are
documented in the development guide. Missing readiness or fixture preparation
fails with instructions to run `up`, not an implicit startup.

HTTPS is published only on `127.0.0.1`. Use `localhost` in URLs: its certificate
is signed by the stand's separate CA. Tests verify that CA; Chromium pins the
verified leaf key in an isolated session. No system trust store is changed.
GitLab and Runner communicate over the internal Compose network. Only the
synthetic fixture repositories are mutated. Initialization provides groups named
`fixtures` and `manual`, with checkout-owned unique paths. A separate account owns
`manual`; its credentials are initialization-only and cannot be selected as an
automation actor. Ordinary runs never read, enumerate, hash, mutate or clean its
contents or local personal directories. API requests reject project catalogs and
non-fixture targets before transport. Existing legacy `free` data are left in place,
not fingerprinted or migrated. Do not put production data into this stand.
For personal login, use `users.manual` in the private `state/fixtures.json`;
create your own projects inside the printed manual group. Do not share that file.

## Evidence and limits

Ignored state remains in `.build/gitlab-test/gitlab-workflows/state/`, with private
credentials and isolated Git/glab/XDG directories. Reports live separately in
`reports/<run>/result.json`; `reports/latest.json` points to the last operation.
Reports retain failures, versions, run duration, container resource samples,
API observations, traces and browser screenshots. Failures and timeouts return
nonzero. Preparation is checked separately from authorized synthetic writes.
`browser-network.json` retains XHR/fetch URLs, methods, statuses and transport
errors without request headers, cookies or bodies, including on a failed UI check.
`preflight.json` records Engine/Compose, pinned image identities, CLI/browser versions,
checkout SHA/dirty state and host resources. `automation-access.json` records scoped
driver requests, not manual content. Browser state uses isolated XDG directories
and a short private temporary socket directory. Health checks require the startup
post-reconfigure hook to finish before calling Puma with full dependency readiness.
The completion marker lives in container tmpfs and is cleared before reconfigure;
it cannot survive a container restart. This prevents fixture checks from racing
Omnibus's delayed Workhorse restart, even when Puma and the login page already
respond successfully. Startup failures remain failures; API writes are not retried.

| Scenario | Expected result | Server postcondition |
| - | - | - |
| Accounts and reruns | Owned identities reused | Authenticated IDs, stable project IDs |
| Pagination | Real glab follows multiple pages | All three run-specific issues present with `per_page=1` |
| Helper catalog/roles | Real MR/release collectors run as author and reviewer; reviewmatic and triage consume a reused 101-label catalog | Every fixture label is present; MR/release collectors report at least two pages |
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
| Mutation faults | Cancel before dispatch, cancel/timeout after a real write while suppressing its response | Nonzero job; one exact issue after controlled retry or read-only reconciliation; ambiguous writes are not blindly repeated |
| Task triage publication | Collect and render with the real helper, then copy commands as author/reviewer | No preparation write; exact title/description/labels/milestone and supported CE link |
| Release workflows | Exact inventory includes a merged component, reviewer and closing issue; record bound readiness; copy pre/post-merge runbooks | Complete inventory, literal MR/release content and exact publication SHA; deterministic decisions are not model assessments |
| Retention boundary (separate lifecycle task) | Down/up and recreate retain fixtures | Fixture branch/tag trees, issues/MR discussions and metadata match; no manual-content comparison is claimed |

The harness does **not** yet prove the complete acceptance matrix. Missing cases
include exhaustive helper resource pagination/roles for all six workflows, reviewmatic's
old/new/context and single-suggestion commands, TUI issue and separate thread-state
actions, same-file grouped stale-state recovery, task
triage information-request lifecycle and stale analysis, full release negative/role
coverage and in-flight TUI mutation cancellation/retry. Fixture-only retention checks
do not inspect any manual payloads or claim that their contents were compared.
Deterministic receipt inputs are not real critic runs.
Do not interpret baseline API checks or offline suites as those missing proofs.
Until that mandatory coverage is implemented, `test` records the missing cases
and returns nonzero even when every available baseline scenario passes.
Reports include UTC `started_at`, per-scenario pass/fail/not-run and durations,
plus initial/final resource samples. Ordinary tests never perform down/up;
`task test:integration:lifecycle` explicitly checks retention in the same dev environment.
A transport fault wrapper is explicitly marked as injection;
it is never used as evidence of a GitLab network response.
`browser-remap-<sha>.json` records the real UI serializer before navigation.
MR diff refs may advance while the remaining discussion is inactive at its old
position. The browser waits for an active exact-head position, then navigates once
and waits for the scoped discussion, without repeated page loads or mutation retries.
The TUI driver waits for a complete synchronized frame and the detail action footer,
not a note title that is also present in the overview.
Release announcement commands keep their prompt attachment without the incompatible
`--unique` flag. A missing response requires inspecting the actual discussion before
repetition; an advisory marker is not proof of a write or duplicate protection.

## Cleanup

`task env:gitlab:clean` immediately deletes GitLab data, including manual projects
and private credentials, without confirmation. Reports survive. Use
`task env:gitlab:recreate` to recreate containers without deleting data. Ordinary
tests never clean; cleanup safety is checked offline, not on another disposable server.

## Optional live

```sh
EVAL_HOST=opencode EVAL_MODEL=provider/model EVAL_TIMEOUT=300 \
  EVAL_MAX_TOKENS=12000 EVAL_MAX_COST=1 task test:integration:gitlab:live
```

Use actual values and explicitly supplied provider credentials/configuration.
Existing `opencode`/`codex` host adapters are reused. Global host credentials are
not copied. Live checks the MR-preparation artifact and the manual publication
boundary, not just the agent's claim. This is not a live assessment of all six
workflows. Live has its own fixture/report and does not rerun the deterministic
matrix. Missing settings, credentials or token/cost telemetry fail closed.
Timeout bounds execution; returned telemetry checks budgets after execution,
not as a prepaid cost ceiling. Live is optional and requires no CI job.

On failure, retain state, inspect the report and `task env:gitlab:logs`, fix the cause
and repeat. Never reset persistent data merely to obtain a green test.
