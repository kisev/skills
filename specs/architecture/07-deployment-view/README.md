# Deployment View

Validated release tags run the complete gate, then deploy a standard well-known
index and content-addressed portable archives to `https://kisev.github.io/skills`
and publish one preflighted `@kisev/skills-opencode` tarball. Remote bytes,
registry signatures, and provenance are verified before the GitHub Release is
created. Git contains deduplicated authored sources, not installable skills.
Runtime state is local to its declared global/project owner; ordinary tests and
offline evals run without network or credentials.
