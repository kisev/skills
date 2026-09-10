# Context and Scope

Users invoke portable skills or generated commands. OpenCode loads the package,
which exposes a core infrastructure plugin, selectable plugins, package tools,
and host-agent routing. Git is the distribution source; local project/global
configuration and runtime state are neighboring boundaries. External GitLab,
Mattermost, and host APIs are accessed only by capabilities that declare them.

Out of scope are new repository gates, runtime redesign, and retired public APIs.
