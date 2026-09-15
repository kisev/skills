# OpenCode Integration

[Русский](README.ru.md)

`@kisev/skills-opencode` is the first-class OpenCode-specific component of
Agent Skills. It complements the portable skills but has its own installation,
update, and removal lifecycle.

## What It Adds

- OpenCode slash-command adapters for installed portable skills and package tools.
- Six fixed agents: `manager`, `architect`, `mapper`, `worker`, `review`, and
  `critic`.
- Capability routing, doctor, reconcile, and agent-profile tooling.
- Optional `rules-injector`, `rtk`, and `zed-bell` plugin wrappers.

The package does not contain, install, update, or remove portable skills.

## Requirements

- Node.js 22 or later.
- OpenCode `>=1.18.29 <1.19.0`.
- A persistent npm project that owns the dependency.

## Project Install

Install the package in the repository's npm project and preview the managed
assets:

```shell
npm install --save-exact @kisev/skills-opencode
npx --yes @kisev/skills-opencode@latest install --scope project --dry-run
```

Run the exact confirmation command printed by the preview. If the selected
assets need core integration, add the package to the user-owned OpenCode
configuration while preserving existing entries:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@kisev/skills-opencode"]
}
```

Restart OpenCode after activation or asset changes. The installer does not edit
`opencode.json` and command adapter selections do not install portable skills.

## Documentation

The canonical documentation lives in `docs/`, not in the package source:

- [Complete OpenCode integration guide](https://github.com/kisev/skills/blob/main/docs/how-to/opencode-integration.md)
- [Portable skills guide](https://github.com/kisev/skills/blob/main/docs/how-to/portable-skills.md)
- [Documentation index](https://github.com/kisev/skills/blob/main/docs/README.md)

The complete guide covers global installation, asset selection, confirmation,
activation, doctor, update, reconcile, agent profiles, ownership, and uninstall.
