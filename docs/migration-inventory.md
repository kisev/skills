# Migration Inventory

This inventory records the intended split from the Bedrock-managed bundle.
Only `askme` is implemented in this repository at this stage.

| Inventory | Count | Destination | Status |
| --- | ---: | --- | --- |
| Portable skills | 23 | `skills/` | Planned; `askme` is the canary |
| OpenCode-specific skills | 7 | optional OpenCode integration | Planned |

The portable inventory must not inherit Bedrock runtime state, catalog files,
providers, or OpenCode tool names. `agent-profiles`, `capabilities`, `doctor`,
not portable skills in this repository.

Commands become thin OpenCode adapters. They select or invoke a portable skill
but do not become a second workflow implementation. OpenCode agents and plugins
are supplied by the future optional npm package, not by a skill installation.

The migration deliberately does not implement the remaining skills, the npm
package, agents, commands, or plugins.
