# Build, Distribution, and Compatibility

Canonical definitions and shared files generate portable and OpenCode assets.
Generated outputs are checked for parity, reproducibility, and undeclared files.
Portable Pages archives are content-addressed and self-contained; the npm package
is an independent native OpenCode V2 adapter under
[REQ-I-420](../../requirements/interfaces/README.md#req-i-420---native-opencode-v2-interface).
The reviewmatic Python application is a separate Git-subdirectory source invoked
with `uvx` under
[REQ-I-428](../../requirements/interfaces/README.md#req-i-428---run-reviewmatic-from-a-selected-git-ref);
it is not included in the npm release manifest.
The compatibility inventory owns the supported ranges and exact verification
samples separately. Default plugin objects expose only `setup`; hooks operate on
native events and preserve structured tool results without a V1 adapter or host
SDK import at runtime. Mise pins only V2 through its npm backend. Installed-tarball
smoke checks cover plugin loading, agent discovery, and real permission evaluation.
One release manifest binds every Pages file and the exact npm tarball to the tag
and revision. Publication verifies both remote channels before creating the
GitHub Release. Compatibility checks are pinned, hostless where possible, and
no-network/no-secret.
Stable versions are prepared on `dev` and promoted to `main` through a pull
request with a merge commit. Tag publication revalidates that the tagged commit
is on `main` and referenced by an annotated matching tag before external
publication. Gate-successful pushes to `dev` derive a unique prerelease
identifier from the maintained version, workflow run, and revision; this
identifier never chooses the next stable SemVer.
Project release, portable installer, and OpenCode compatibility use separate
authorities. User documentation follows stable channels, while automation,
lockfiles, generated commands, and release artifacts retain checked exact values.
