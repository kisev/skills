# Architecture

This architecture uses the repository's 12 arc42 viewpoints as a compact model
of the current `2.2.1` system. Portable definitions are deduplicated, CI publishes
self-contained well-known archives through GitHub Pages, and the OpenCode core
plugin owns routing, package tools, and lifecycle boundaries.

See [architecture decisions](09-architecture-decisions/README.md) and the
[crosscutting concepts](08-crosscutting-concepts/README.md) for shared rules.
