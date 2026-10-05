# Deployment View

Validated release tags run the complete gate, deploy the stable well-known
distribution at `https://kisev.github.io/skills`, and publish preflighted
`@kisev/safe-fs`, `@kisev/memomatic`, `@kisev/taskmatic`, and `@kisev/agentomatic` tarballs in
dependency order under npm `latest`. The release manifest binds each member's
version, dependency pins, and digest. A push to `dev` runs the
complete publication gate, then updates `https://kisev.github.io/skills/dev` and
npm `dev` with a unique
technical snapshot version. Every Pages artifact contains both channels so one
deployment cannot erase the other. Stable remote bytes, registry signatures,
and provenance are verified before the GitHub Release is created. Dev creates no
GitHub Release. Git contains deduplicated authored sources, not installable skills.
Runtime state is local to its declared global/project owner; ordinary tests and
offline evals run without network or credentials.

The reviewmatic application is not an npm release member. Users run its Python
CLI from this repository with `uvx --from` and a selected Git ref: an exact
release tag for stable skills or the moving `dev` branch for development. It is
not published to PyPI and does not require a persistent `uv tool install`.

The root `docker-compose.yml` supplies one persistent `skills-dev` project with
service-scoped Taskfile lifecycle commands and grouped `env:*` dependencies.
Infrastructure configuration lives under `dev/`; test scenarios and helpers live
under `tests/integration/`, not application packages. A bounded helper adopts
verified former default volumes using ignored `.build/env/compose.env` mappings,
prepares fixtures after Compose readiness and cleans only explicitly selected data.
Actual lifecycle commands remain in Taskfile; ordinary tests only connect to ready
services. Explicit clean removes selected data without prompts or digests and
retains reports. Separate lifecycle tests interrupt this same environment; they
never create another server or clean persistent data.

Its Mattermost services supply the persistent
[Mattermost test environment](../../requirements/functional/README.md#req-f-547---automate-a-persistent-local-mattermost-test-environment),
including [card verification](../../capabilities/skills/mattermost.md#req-f-546---prepare-opt-in-bilingual-discussion-cards).
It runs Mattermost and PostgreSQL on an internal Docker network, with Caddy
publishing HTTPS on host loopback only. PostgreSQL uses local-test trust
authentication and has no host port. Named volumes retain test accounts, posts,
and the local CA; stopping the stack does not delete them. The public CA can be
exported under ignored `.build/` without installing host trust. Test credentials
and publication plans use isolated XDG directories. A private Python driver uses
the container-local admin socket to reconcile owned fixtures. The browser uses an
isolated session with a verified leaf-key pin, without changing host trust.
Historical local state and reports retain their separate roots; cleanup checks
checkout ownership and rejects symlinks. Live evaluation
uses the existing host command and budget adapters with explicit provider settings.
The stack is opt-in, outside
portable archives and the ordinary offline quality gate; its patch image can be
overridden and does not establish compatibility with an untested production patch.

The same Compose project's GitLab services support the
[GitLab workflow verification contract](../../requirements/functional/README.md#req-f-548---verify-gitlab-workflows-against-a-persistent-local-ce-server).
It pins CE `18.11.11-ce.0`, Runner `v18.11.0` and repository glab `1.120.0`.
Caddy exposes a separate local CA over loopback HTTPS; GitLab and the shell
Runner use an internal network. Runner has neither privileged mode nor a host
Docker socket. The host driver provisions identities through container-local
Rails, then verifies actual API, CLI, pipeline and browser state. Isolated
Git/glab/XDG credentials and evidence live under ignored `.build/gitlab-test/`.
The driver reuses Mattermost's atomic private-state utilities, verified browser
driver and existing live host/budget adapters. Server and runner named volumes
are distinct from retained local reports. The ordinary offline gate checks the
harness contracts without starting this deployment.
The GitLab health probe requires completion of the container startup
post-reconfigure hook before calling Puma with full dependency readiness.
A tmpfs marker, cleared by the pre-reconfigure hook and lost on container restart,
prevents fixture checks from racing Omnibus's delayed Workhorse restart.
Fixture identities own the automation group; a distinct initialization-only
identity owns the manual group. The driver's API allowlist rejects project
catalogs and non-fixture targets before transport. Fixture-only retention checks
do not traverse personal directories. UI remap evidence records the discussion
serializer's current position independently of MR diff refs. Live runs use a
separate fixture and do not inherit the deterministic suite's coverage status.

Network exposure is limited to release publication, capabilities whose contracts
declare an external API, and the opt-in loopback test stacks described above;
ordinary tests and offline evals have none.
Secrets remain in the invoking environment or host-managed credential boundary
and are not placed in Git, generated distributions, archives, reports, or
diagnostics. Crosscutting redaction and mutation rules provide
[REQ-Q-003](../../requirements/quality/README.md#req-q-003---secret-safety), while
release boundaries provide
[REQ-Q-008](../../requirements/quality/README.md#req-q-008---verify-release-promotion).

Ordinary CI materializes portable skills independently in each matrix job and
runs independent quality tasks in parallel. Reproducibility checks compare the
results; avoiding artifact transfer preserves executable file modes. Publication
verifies all manifest members before completion as required by
[REQ-F-004](../../requirements/functional/README.md#req-f-004---publish-one-verified-release).
