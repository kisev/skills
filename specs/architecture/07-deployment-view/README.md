# Deployment View

Validated release tags deploy a standard well-known index and content-addressed
portable archives to `https://kisev.github.io/skills` and publish the separately
owned `@kisev/skills-opencode` npm package. Git contains deduplicated authored
sources, not installable skills. Runtime state is local to its declared
global/project owner; ordinary tests and offline evals run without network or
credentials.
