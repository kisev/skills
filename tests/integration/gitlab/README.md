# Local GitLab workflow tests

[Русский](README.ru.md)

These tests use the shared [development environment](../../../dev/README.md):
GitLab CE `18.11.11-ce.0`, GitLab Runner `v18.11.0`
and the repository's `glab 1.120.0`. Runner executes shell jobs inside its own
container, with no host Docker socket. Docker executor and paid EE features are
outside scope. Ordinary `task check` needs no running server.

## Run

Prerequisites: Linux, Docker Engine, Compose v2, OpenSSL, Git and the Mise toolchain.
Chromium and `agent-browser` are required only by the separately invoked deferred browser run.
Allow several minutes for GitLab startup and enough memory for GitLab.
Provision the pinned images before running the tests.
Preflight stops with diagnostics if they are missing; it never substitutes versions.

```sh
mise install
task generate
task env:gitlab:up
task test:integration:gitlab:preflight
task test:integration:gitlab
```

All GitLab browser tests are deferred from this stage's blocking API/backend acceptance.
They remain separately invokable; ordinary `test` and `preflight` neither launch nor
require a browser. Deferred scenarios are not passing evidence, and UI behavior
remains unverified.

```sh
mise exec -- agent-browser install
task test:integration:gitlab:browser
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
Its `transport` entries retain Chromium `Network.loadingFailed` errors from a
private temporary HAR started after login. The raw HAR is deleted after extracting
allowlisted metadata; `--content none` alone does not remove headers or cookies.
Status `0` with `net::ERR_NETWORK_CHANGED` is a browser transport failure, not an
HTTP rejection. Diagnose host address/route changes rather than reloading until
green, increasing waits or changing host network settings from the test.
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
| Helper resources | Shipped Python pagers read real multi-page catalogs as both roles | Complete IDs/counts for issues, labels, milestones, tags/releases, MR/CI, trees and relationships; issue links are tested at CE's 100-link boundary, a whole-collection API that ignores pagination |
| Issue metadata and links | CE accepts labels, milestones, `relates_to` | GET issues and links returns exact metadata and target |
| Tags and releases | Release identifies fixture commit | GET release returns the exact SHA |
| Shell CI | Success, allowed failure, child job execute | Exact-SHA terminal pipeline, real job states and trace markers |
| Inline comments | Old/new/context positions accepted | Returned position and head SHA match requested payload |
| Suggestions | Server recognizes a suggestion | Nonempty server suggestion metadata; browser application checks resulting file |
| Replies and threads | Author reply; separate resolve/reopen | Author ID and resolved flag read back after each operation |
| Negative API | Outsider and invalid line rejected | Expected non-2xx status, never a successful write |
| MR/release preparation | Collect complete exact-head evidence without publication | Discussions unchanged, incomplete helper evidence rejected |
| MR publication | Copy the generated commands, as reviewer and author | Exact literal title/description/labels; human discussion notes unchanged |
| Task publication | Execute copied marker-wrapped GraphQL commands as author and reviewer | Real issue title, labels, milestone and author ID match each role's plan |
| Task preparation/triage | Local plan and actual collection | Issue catalog unchanged during preparation |
| Reviewmatic | Run the Python application, prepare, presentation-repair, then copy runbook commands | Findings, suggestions and fixture receipts retained; real grouped suggestions and replies published |
| CI-only refresh | Rerun real shell CI on the same SHA, then finish the existing draft | Supplemental CI snapshot; original findings/evidence/receipts retained; no repeated `startReview` |
| Material refresh | Collect changed conversations without publishing or rebinding receipts | Findings/dispositions and original draft preserved; new receipts empty; last finalized plan remains readable |
| Same-file API/backend recovery | The real API applies two parts of one file sequentially | Exact SHAs, files and partial/full flags; backend reassessment retains findings without rebinding receipts; browser remapping is checked only separately |
| Triage information lifecycle | Copy request, first ping, second ping, message and separate closure; reject old analysis and restore a missing CE link | Ordered real note IDs/authorship; no closure before its command; stale analysis makes no write; exactly one restored relation |
| Browser (deferred) | A separate explicit run checks inline placement, single/cross-file/same-file application and remapping | Screenshots, exact files and application flags; not part of the mandatory API/backend run |
| Transport fault/retry | Inject CLI failure, then retry the actual collector | Failure is nonzero; retry has complete evidence; server unchanged |
| Mutation faults | Cancel before dispatch, cancel/timeout after a real write while suppressing its response | Nonzero job; one exact issue after controlled retry or read-only reconciliation; ambiguous writes are not blindly repeated |
| Task triage publication | Collect and render with the real helper, then copy commands as author/reviewer | No preparation write; exact title/description/labels/milestone and supported CE link |
| Release workflows | Each role collects inventory/readiness and copies pre/post-merge runbooks using its own closing issue | Complete inventory, literal MR/release content, announcement author and exact publication SHA; invalid bindings, incomplete inventory, premature post-merge and invalid readiness are rejected without writes; deterministic decisions are not model assessments |
| Retention boundary (separate lifecycle task) | Down/up and recreate retain fixtures | Fixture branch/tag trees, issues/MR discussions and metadata match; no manual-content comparison is claimed |

The API/backend report claims complete coverage only when all mandatory checks pass:
resource pagination, both roles, copied commands, same-file reassessment, triage
lifecycle and release inventory/readiness/publication with negative cases.
Baseline API checks or a focused scenario alone do not establish that result.
The reusable resource catalog supplies real second pages; issue links instead use
the observed CE limit of 100 and its whole-collection semantics. Stress CI jobs and
bridges are not played; ordinary shell-CI scenarios independently verify execution.
Two consecutive full API/backend runs establish repeatability. Fixture-only retention checks
do not inspect any manual payloads or claim that their contents were compared.
Deterministic receipt inputs are not real critic runs.
Do not interpret API/backend evidence as verified browser behavior or model quality.
Whenever mandatory coverage is incomplete, `test` records the missing cases
and returns nonzero even when every available baseline scenario passes.
Reports include UTC `started_at`, per-scenario pass/fail/not-run and durations,
plus initial/final resource samples. Ordinary tests never perform down/up;
`task test:integration:lifecycle` explicitly checks retention in the same dev environment.
A transport fault wrapper is explicitly marked as injection;
it is never used as evidence of a GitLab network response.
`browser-remap-<sha>.json` records the real UI serializer before navigation.
MR diff refs may advance while the remaining discussion is inactive at its old
position. The browser waits for an active exact-head position, selects the matching
source-head `diff_id` (head-diff previews may use a synthetic merge SHA), then navigates once
and waits for the scoped discussion, without repeated page loads or mutation retries.
Reviewmatic is the Python application; it has no TUI or in-app publication action.
Backend preparation, repair, refresh, finalization and copied runbook commands
remain mandatory. All GitLab browser scenarios are deferred and are reported
separately from missing mandatory backend coverage.
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
