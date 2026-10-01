# Persistent Mattermost test environment

[Русский](README.ru.md)

Run automated checks for `mattermost` and `mattermost-triage` against a real
Mattermost server. The environment persists across runs and is separate from
portable archives and the ordinary `task check` gate. Prerequisites: Linux,
Docker Engine, Compose v2 with `up --wait`, OpenSSL, and the Mise toolchain.
Images and browser binaries are downloaded only when needed.

## First run and repeat runs

From the repository root:

```sh
task mattermost:config
mise install
mise exec -- agent-browser install
task mattermost:test
```

Tasks default to the standalone `docker-compose` executable. With the Docker
CLI plugin, add `COMPOSE="docker compose"` to each task invocation. All commands
also work directly with `docker compose -f apps/mattermost-test/compose.yml`.

The test task materializes the skills, runs their contract/regression suites,
starts the stack, reconciles owned accounts, team, channels, direct/group chats,
and messages, and configures isolated credentials automatically. Repeat the same
command; no manual signup, token entry, sending, or screenshot review is needed.
`task mattermost:init` initializes/reconciles without running tests and prints
the free-zone URL. `task mattermost:up` only starts the containers.

The default URL is `https://localhost:8443`. Tests verify TLS against the local CA;
an isolated Chromium session pins the verified leaf public key. A process-local
CA bundle includes system roots plus the test CA, so browser-tool bootstrap and
optional provider connections still work. No host/browser trust store or existing
browser profile is modified, and certificate validation in the skills remains on.
For your own browser, `task mattermost:ca` exports the public CA for optional
manual import. The private CA stays in Docker. Use `localhost`, not `127.0.0.1`,
in browser URLs because that is the certificate name.

The default image is `mattermost/mattermost-team-edition:10.10.3`, an available
fixed patch of the 10.10 series. The official Team and Enterprise repositories
did not provide a `10.10.19` tag when this stack was prepared. This is not proof
of exact production-patch compatibility. Select an available matching image with
`MM_TEST_IMAGE`. `MM_TEST_PORT` changes the localhost HTTPS port (default 8443),
and `MM_TEST_PROJECT` isolates Compose resources (default `mattermost-cards`).
Keep the same variables for subsequent commands. Do not point
an older image at data already migrated by a newer server; use a new project.

## State and ownership

Named volumes retain server data and the CA. Per-project local state is under
`.build/mattermost-test/<project>/state/`; reports are in the sibling `reports/`.
Generated credentials are in private `fixtures.json`; do not copy them into
chat, command arguments, or Git. Skills receive isolated XDG paths. Reports and
screenshots contain only local test evidence and remain outside Git.

Fixture identities and the team are stable; tests manage their own named
channels and messages. The `free` channel is for manual experiments and is not
rewritten by normal checks. Test publications append owned examples to test
channels. A lock rejects concurrent operations on the same project. A Compose
project owned by another checkout is rejected; use another `MM_TEST_PROJECT`
and port rather than taking it over.

## Coverage and results

| Area | Evidence |
| - | - |
| Reads | Real pagination over 205 fixtures, threads, direct/group chats, participants, reactions, time bounds, transcript continuation |
| Auth/cache | Real browser credential flow, missing auth, denied private channel, cache hit/clear, refresh and partial read-many |
| Publications | Real text/file/card POST, idempotent replay and injected lost-response recovery by subsequent GET |
| Triage | Real collection, citation rejection, artifacts, reply publication, incremental watermark and unresolved carryover |
| Cards | Standard/custom RU/EN, normal/narrow thread views, near-budget inputs and a deliberately oversized negative control |
| Lifecycle | Repeat bootstrap and free-zone preservation; separate reset test |
| Fault boundaries | Portable unit suites cover malformed state, timeouts, stale/tampered actions, ambiguous upload and partial responses |

Each real-server check records pass/fail and evidence in a timestamped
`result.json`; `reports/latest.json` points to it. Browser checks assert rendered
content, collapse and overflow, and retain screenshots. Any failed assertion
returns nonzero. A timeout is a failure, never a skipped success. This local
test harness may execute publication helpers against its own fixtures; the
[ordinary skill publication workflow](../../skills/mattermost/references/workflow.md#publication)
remains manual. Card examples and limits are in the
[card guide](../../skills/mattermost/references/cards.md).

## Optional real-agent level

```sh
EVAL_HOST=opencode EVAL_MODEL=provider/model EVAL_TIMEOUT=300 \
  EVAL_MAX_TOKENS=12000 EVAL_MAX_COST=1 task mattermost:live
```

Configure actual values and provider authentication before this command. Supported
hosts are `opencode` and `codex`, using the existing repository host adapters.
Provider keys are explicitly inherited from standard provider environment
variables; OpenCode also accepts `OPENCODE_CONFIG_CONTENT` and
`OPENCODE_CLI_CONFIG_CONTENT`. Configure noninteractive host permissions there.
Global host credentials/configuration are not copied. Installed host CLI and a
configured provider are prerequisites. Missing settings fail before startup.

The live workspace persists under the project's state. Real skills must read an
exact fixture, prepare triage artifacts and a card plan, and preserve the
manual-send boundary. The harness checks artifacts rather than accepting a
model's success claim. Redacted host output, usage, cost and budget assertions
are retained. Budget accounting follows the existing eval runner: timeout bounds
execution, token/cost checks use returned telemetry after execution, not a prepaid
spending cap. Missing cost/token telemetry is incomplete and cannot pass. The
deterministic level needs no model or provider credentials.

## Explicit reset

```sh
task mattermost:reset
MM_RESET_CONFIRM=the_preview_digest task mattermost:reset
task mattermost:test-reset
```

The first command only previews the exact project resources and digest. The
confirmed command deletes that server's volumes, free zone, credentials, local
skill state and test browser session, then initializes again. Reports survive.
It rejects a changed scope, foreign project, unexpected volumes, or symlinked
state. The reset test uses its own randomly named disposable project and verifies
that the primary stand and reports survive. Normal tests never reset the stand.

## Stop and troubleshoot

```sh
task mattermost:logs
task mattermost:down
```

Down retains named volumes: accounts, messages, database, and the CA survive.
Inspect `docker compose -f apps/mattermost-test/compose.yml ps` if startup times
out. A busy port can be changed through `MM_TEST_PORT`; a missing Compose plugin
can be addressed with the standalone executable. Certificate export may need
retrying briefly after first startup while Caddy creates its local CA.

This is a local test stack: only HTTPS is bound to `127.0.0.1`;
PostgreSQL has no host port and uses passwordless trust on an internal network.
Email notifications, telemetry, and plugins are disabled. The healthcheck uses
the bundled `mmctl --local system status` over a container-local Unix socket;
the Mattermost image does not require a shell or curl.
The optional Python driver provisions fixtures through that same private socket;
it is not a public API service. Do not expose this stack as a shared or production
deployment. On a failed test, inspect its report and `task mattermost:logs`, fix
the cause and repeat. Do not delete persistent state merely to make a test pass.
