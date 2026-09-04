# Agent Skills

This repository is the public source of portable Agent Skills and, later, an
optional npm package for OpenCode integration.

## Install a skill

Install the canary skill directly from this repository with `npx skills`:

```shell
npx skills add . --skill askme --agent codex --agent opencode --copy
```

Use `npx skills add . --list` to inspect the skills available in the checkout.

## Boundaries

- `skills/` contains portable, self-contained skills installable by `npx skills`.
- `packages/opencode/` documents the future optional package boundary for
  OpenCode agents, commands, and plugins. It is not implemented yet.
- There is no user-facing CLI. Python is used only by skill runners and
  maintainer scripts.
- A skill must work after installation without reading files outside its own
  directory. Shared source material is copied deterministically into each
  consumer skill before release.

The repository is MIT licensed. See [LICENSE](LICENSE).

## Maintainer checks

```shell
python3 scripts/sync_shared.py
python3 scripts/sync_shared.py --check
python3 -m unittest discover -s tests -v
npx --yes skills add . --list
uvx --from skills-ref agentskills validate skills/askme
```

The `npx skills` command is the installation interface; this repository does
not add another installer or a hidden OpenCode dependency.
