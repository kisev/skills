# Context and Scope

Users invoke portable skills or generated commands. OpenCode loads the package,
which exposes a core infrastructure plugin, selectable plugins, the `route` tool,
and host-agent routing. Git is the authored source; CI-built GitHub Pages
archives are the portable distribution. Local project/global configuration and
runtime state are neighboring boundaries. External GitLab, Mattermost, and host
APIs are accessed only by capabilities that declare them.

The local user and repository, the installed host/runtime, publication
infrastructure, and each external service are separate trust boundaries. Prompts,
repository content, tool output, credentials, and returned external content cross
those boundaries only through the declared capability surface. This context owns
the external subjects and crossings; runtime exposure and secret placement are in
the [deployment view](../07-deployment-view/README.md), while authorization and
sensitive-data handling are [crosscutting concepts](../08-crosscutting-concepts/security-trust-mutations.md).
These boundaries support [REQ-I-002](../../requirements/interfaces/README.md#req-i-002---command-interface)
and [REQ-Q-003](../../requirements/quality/README.md#req-q-003---secret-safety).

Out of scope are capability runtime redesign and restoration of retired public APIs.
