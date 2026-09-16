# Context and Scope

Users invoke portable skills or generated commands. OpenCode loads the package,
which exposes a core infrastructure plugin, selectable plugins, the `route` tool,
and host-agent routing. Git is the authored source; CI-built GitHub Pages
archives are the portable distribution. Local project/global configuration and
runtime state are neighboring boundaries. External GitLab, Mattermost, and host
APIs are accessed only by capabilities that declare them.

Out of scope are capability runtime redesign and restoration of retired public APIs.
