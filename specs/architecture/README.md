# Architecture

This architecture uses the repository's 12 arc42 viewpoints as a compact model
of the current `2.0.0` system. The OpenCode package is an adapter around portable
skills, direct Git distribution is independently self-contained, and the core
plugin owns routing, package tools, and lifecycle boundaries.

See [architecture decisions](09-architecture-decisions/README.md) and the
[crosscutting concepts](08-crosscutting-concepts/README.md) for shared rules.
