# skillmate

The installer-configurator for the repository's portable Agent Skills:
installs skills, lays out their command surfaces, and configures hosts
for Codex, Claude, and OpenCode, in project and global scopes, with a
preview-and-confirmation safety model.

Skeleton stage: commands parse arguments and print empty plan previews;
the lifecycle is specified in the `spec-skillmate` OpenSpec change.

## Run

```shell
uvx --from apps/skillmate skillmate --help
```
