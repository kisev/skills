# Deployment View

Validated release tags run the complete gate, deploy the stable well-known
distribution at `https://kisev.github.io/skills`, and publish one preflighted
`@kisev/skills-opencode` tarball under npm `latest`. A push to `dev` runs the
complete publication gate, then updates `https://kisev.github.io/skills/dev` and
npm `dev` with a unique
technical snapshot version. Every Pages artifact contains both channels so one
deployment cannot erase the other. Stable remote bytes, registry signatures,
and provenance are verified before the GitHub Release is created. Dev creates no
GitHub Release. Git contains deduplicated authored sources, not installable skills.
Runtime state is local to its declared global/project owner; ordinary tests and
offline evals run without network or credentials.

Network exposure is limited to release publication and capabilities whose
contracts declare an external API; ordinary tests and offline evals have none.
Secrets remain in the invoking environment or host-managed credential boundary
and are not placed in Git, generated distributions, archives, reports, or
diagnostics. Crosscutting redaction and mutation rules provide
[REQ-Q-003](../../requirements/quality/README.md#req-q-003---secret-safety), while
release boundaries provide
[REQ-Q-008](../../requirements/quality/README.md#req-q-008---verify-release-promotion).

Ordinary CI materializes portable skills once, transfers that immutable build
artifact to dependent jobs, and runs independent quality tasks in parallel.
