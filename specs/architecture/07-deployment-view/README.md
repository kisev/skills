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

The optional `apps/mattermost-test/compose.yml` deployment supplies the persistent
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
Per-project state and reports have separate roots; reset checks project ownership
and a resource-bound digest, retains reports, and reinitializes. Live evaluation
uses the existing host command and budget adapters with explicit provider settings.
The stack is opt-in, outside
portable archives and the ordinary offline quality gate; its patch image can be
overridden and does not establish compatibility with an untested production patch.

Network exposure is limited to release publication, capabilities whose contracts
declare an external API, and the opt-in loopback test stack described above;
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
