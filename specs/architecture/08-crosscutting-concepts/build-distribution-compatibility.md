# Build, Distribution, and Compatibility

Canonical definitions and shared files generate portable and OpenCode assets.
Generated outputs are checked for parity, reproducibility, and undeclared files.
Portable Pages archives are content-addressed and self-contained; the npm package
is an independent OpenCode adapter supporting all patches of `1.18.x` and `2.0.x`.
The compatibility inventory owns the supported ranges and exact verification
samples separately. One default object exposes V1 `server` and V2 `setup`;
API adapters share routing and optional-plugin behavior without importing a
host SDK at runtime. Mise pins both CLI generations through its npm backend.
Installed-tarball smoke checks cover each minor's current patch.
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
