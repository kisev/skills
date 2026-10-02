# Mattermost integration tests

[Русский](README.ru.md)

Run automated checks for `mattermost` and `mattermost-triage` against a real
Mattermost server in the shared [development environment](../../../dev/README.md).
The environment persists across runs and is separate from
portable archives and the ordinary `task check` gate. Prerequisites: Linux,
Docker Engine, Compose v2 with `up --wait`, OpenSSL, and the Mise toolchain.
Images and browser binaries are downloaded only when needed.

## First run and repeat runs

From the repository root:

```sh
mise install
mise exec -- agent-browser install
task env:mattermost:up
task test:integration:mattermost
```

Tasks default to the standalone `docker-compose` executable. With the Docker
CLI plugin, add `COMPOSE="docker compose"` to each task invocation. All commands
use the root `docker-compose.yml` and the generated `.build/env/compose.env`.

`env:mattermost:up` starts the service, reconciles owned accounts, team, channels,
direct/group chats and messages, and prints the free-zone URL. The test task
materializes skills and runs contract/regression and server checks against this
ready service; it never starts/stops containers or initializes accounts. Missing
readiness or fixtures fails with instructions to run `up`. Repeat the test command
without manual signup, token entry, sending or screenshot review.

The default URL is `https://localhost:8443`. Tests verify TLS against the local CA;
an isolated Chromium session pins the verified leaf public key. A process-local
CA bundle includes system roots plus the test CA, so browser-tool bootstrap and
optional provider connections still work. No host/browser trust store or existing
browser profile is modified, and certificate validation in the skills remains on.
For your own browser, the public CA is in
`.build/mattermost-test/mattermost-cards/state/root.crt` for optional manual import.
The private CA stays in Docker. Use `localhost`, not `127.0.0.1`,
in browser URLs because that is the certificate name.

The default image is `mattermost/mattermost-team-edition:10.10.3`, an available
fixed patch of the 10.10 series. The official Team and Enterprise repositories
did not provide a `10.10.19` tag when this stack was prepared. This is not proof
of exact production-patch compatibility. Select an available matching image with
`MM_TEST_IMAGE`. `MM_TEST_PORT` changes the localhost HTTPS port (default 8443),
with one shared `skills-dev` Compose project. Keep the same variables for subsequent
commands. Do not point an older image at data already migrated by a newer server.

## State and ownership

Named volumes retain server data and the CA. Existing local state stays under
`.build/mattermost-test/mattermost-cards/state/`; reports are in the sibling `reports/`.
Generated credentials are in private `fixtures.json`; do not copy them into
chat, command arguments, or Git. Skills receive isolated XDG paths. Reports and
screenshots contain only local test evidence and remain outside Git.

Fixture identities and the team are stable; tests manage their own named
channels and messages. The `free` channel is for manual experiments and is not
read, hashed or rewritten by normal checks. Test publications append owned examples to test
channels. A lock rejects concurrent operations on the same project. A Compose
project owned by another checkout is rejected; resolve that conflict rather than
taking it over. Lifecycle operations belong to Taskfile, not test drivers.

## Coverage and results

| Area | Evidence |
| - | - |
| Reads | Real pagination over 205 fixtures, threads, direct/group chats, participants, reactions, time bounds, transcript continuation |
| Auth/cache | Real browser credential flow, missing auth, denied private channel, cache hit/clear, refresh and partial read-many |
| Publications | Real text/file/card POST, idempotent replay and injected lost-response recovery by subsequent GET |
| Triage | Real collection, citation rejection, artifacts, reply publication, incremental watermark and unresolved carryover |
| Cards | Standard/custom RU/EN, normal/narrow thread views, near-budget inputs and a deliberately oversized negative control |
| Lifecycle (separate task) | Fixture-only down/up, recreate and repeated up in the same environment; manual data not inspected |
| Fault boundaries | Portable unit suites cover malformed state, timeouts, stale/tampered actions, ambiguous upload and partial responses |

Each real-server check records pass/fail and evidence in a timestamped
`result.json`; `reports/latest.json` points to it. Browser checks assert rendered
content, collapse and overflow, and retain screenshots. Any failed assertion
returns nonzero. A timeout is a failure, never a skipped success. This local
test harness may execute publication helpers against its own fixtures; the
[ordinary skill publication workflow](../../../skills/mattermost/references/workflow.md#publication)
remains manual. Card examples and limits are in the
[card guide](../../../skills/mattermost/references/cards.md).

## Optional real-agent level

```sh
EVAL_HOST=opencode EVAL_MODEL=provider/model EVAL_TIMEOUT=300 \
  EVAL_MAX_TOKENS=12000 EVAL_MAX_COST=1 task test:integration:mattermost:live
```

Configure actual values and provider authentication before this command. Supported
hosts are `opencode` and `codex`, using the existing repository host adapters.
Provider keys are explicitly inherited from standard provider environment
variables; OpenCode also accepts `OPENCODE_CONFIG_CONTENT` and
`OPENCODE_CLI_CONFIG_CONTENT`. Configure noninteractive host permissions there.
Global host credentials/configuration are not copied. Installed host CLI and a
configured provider are prerequisites. Missing settings fail before evaluation.

The live workspace persists under the project's state. Real skills must read an
exact fixture, prepare triage artifacts and a card plan, and preserve the
manual-send boundary. The harness checks artifacts rather than accepting a
model's success claim. Redacted host output, usage, cost and budget assertions
are retained. Budget accounting follows the existing eval runner: timeout bounds
execution, token/cost checks use returned telemetry after execution, not a prepaid
spending cap. Missing cost/token telemetry is incomplete and cannot pass. The
deterministic level needs no model or provider credentials.

## Cleanup and lifecycle checks

`task env:mattermost:clean` deletes server data, free-zone messages, credentials
and local skill state immediately without confirmation; reports survive. Use
`task env:mattermost:recreate` to retain data. Ordinary tests never clean.
`task test:integration:lifecycle` explicitly interrupts both dev services and
checks fixture retention without reading free/manual data or creating another stand.
Cleanup safety is checked offline.

## Stop and troubleshoot

```sh
task env:mattermost:logs
task env:mattermost:down
```

Down retains named volumes: accounts, messages, database, and the CA survive.
Inspect `task env:mattermost:status` if startup times
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
deployment. On a failed test, inspect its report and `task env:mattermost:logs`, fix
the cause and repeat. Do not delete persistent state merely to make a test pass.
