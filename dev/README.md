# Development environment

[Русский](README.ru.md)

The root `docker-compose.yml` describes one persistent `skills-dev` project:
GitLab CE `18.11.11-ce.0`, Runner `v18.11.0`, Mattermost `10.10.3`, PostgreSQL
and loopback HTTPS proxies. This is development infrastructure, not a shipped
application or a portable skill. Linux, Docker Engine and Compose v2 with
service-scoped `down` are required. Run `mise install` first.

## Start and operate

```sh
task env:up
task env:status
task env:logs
task env:stop
task env:up
```

Every `env:<operation>` groups `env:gitlab:<operation>` and
`env:mattermost:<operation>` through Taskfile `deps`. Use either service-specific
task to operate just that service and its dependencies. Tasks default to
`docker-compose`; pass `COMPOSE="docker compose"` for the CLI plugin.

| Operation | Effect |
| - | - |
| `up` | Start, wait for readiness, idempotently initialize missing fixture accounts and data |
| `stop` | Stop containers; retain containers, networks and data |
| `down` | Remove selected containers and unused project networks; retain data |
| `restart` | Restart selected containers, wait for readiness and reconcile fixtures |
| `recreate` | Recreate selected containers and reconcile fixtures; retain data |
| `clean` | Remove selected containers, volumes and private fixture/skill state, including manual data; retain reports |
| `status` | Show selected containers, including stopped ones |
| `logs` | Show the last 100 log lines; does not follow indefinitely |

**`clean` deletes data immediately, without a prompt, preview or confirmation
digest.** For example, `task env:gitlab:clean` deletes GitLab manual projects too;
`task env:clean` deletes both services' data. Run `up` afterward to initialize
fresh data. `recreate` is the operation to use when data must survive.

GitLab is at `https://localhost`; Mattermost is at `https://localhost:8443`.
Use `GL_TEST_PORT` or `MM_TEST_PORT` consistently if overriding ports. Full GitLab
workflow tests require port 443 because pinned glab rejects a port in `--hostname`.
`MM_TEST_IMAGE` may select another available Mattermost patch; do not downgrade
an existing migrated database. The default patch does not establish compatibility
with an untested production patch.

## Existing data and certificates

The first `up` verifies the former default projects' ownership, stops/removes
only their containers and adopts their existing named volumes. No volume data
are copied, enumerated or cleaned. Foreign resources are rejected. Old disposable
projects are not adopted or removed. Existing credentials and reports remain at
`.build/gitlab-test/gitlab-workflows/` and `.build/mattermost-test/mattermost-cards/`.
Historical directory names are retained for compatibility, not separate environments.

`.build/env/volumes.json` records the selected volumes;
`.build/env/compose.env` supplies their names to the root Compose file. These
ignored files contain no API credentials. Keep them while retaining server data.
The small `dev/env.py` helper handles adoption, ownership, fixture preparation and
bounded cleanup; Taskfile runs the actual Compose lifecycle commands.

After preparation, direct Compose diagnostics use:

```sh
docker compose -p skills-dev --env-file .build/env/compose.env ps -a
```

HTTPS is bound only to host loopback. Each proxy retains its own CA; neither
system trust nor working credentials are modified. Public certificates are in
the corresponding `state/root.crt`; API credentials are in private
`state/fixtures.json`. Do not share that file. Browser checks use separate sessions
and verified certificate keys. Runner has no host Docker socket. PostgreSQL has
no host port and uses local-development trust on an internal network.

## Tests and recovery

```sh
mise exec -- agent-browser install
task test:integration:gitlab
task test:integration:mattermost
```

Tests require already running, initialized services. They neither start nor stop
containers and do not initialize accounts. Publications target only test fixtures;
GitLab `manual` and Mattermost `free` are not read or compared. Git/glab/XDG state
is kept separate from working installations; this is process-state isolation,
not another server environment. Ordinary `task check` needs no server or provider.
See the [GitLab](../tests/integration/gitlab/README.md) and
[Mattermost](../tests/integration/mattermost/README.md) test guides for coverage,
browser prerequisites, reports and optional live evaluation.
`agent-browser` is required for Mattermost and separately invoked GitLab browser tests.
Mandatory GitLab API/backend acceptance does not require a browser; UI coverage is deferred.

`task test:integration:lifecycle` explicitly interrupts both services to verify
down/up, recreate and repeated up against fixture snapshots in the same environment.
It never invokes clean or creates another stand; avoid running it during manual work.
Reports are under `.build/env/reports/`. Cleanup safety is verified offline, without
deleting the running environment's data.

On startup failure inspect `env:<service>:status` and `env:<service>:logs`, correct
the cause and repeat `up`; do not use `clean` just to get a passing test. GitLab
readiness waits for the startup post-reconfigure hook before checking Puma and
its dependencies, so delayed Workhorse restarts cannot race fixture checks.
An ownership failure requires resolving the resource conflict, not taking over
another checkout's containers or volumes.
