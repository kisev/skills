# Deployment View

Validated release tags run the complete gate, then deploy a standard well-known
index and content-addressed portable archives to `https://kisev.github.io/skills`
and publish one preflighted `@kisev/skills-opencode` tarball. Remote bytes,
registry signatures, and provenance are verified before the GitHub Release is
created. Git contains deduplicated authored sources, not installable skills.
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
