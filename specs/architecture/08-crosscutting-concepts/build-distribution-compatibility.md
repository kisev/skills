# Build, Distribution, and Compatibility

Canonical definitions and shared files generate portable and OpenCode assets.
Generated outputs are checked for parity, reproducibility, and undeclared files.
Portable Pages archives are content-addressed and self-contained; the npm package
is an independent OpenCode adapter with peer range `>=1.18.29 <1.19.0`.
One release manifest binds every Pages file and the exact npm tarball to the tag
and revision. Publication verifies both remote channels before creating the
GitHub Release. Compatibility checks are pinned, hostless where possible, and
no-network/no-secret.
Every release commit first passes a clean remote pre-tag gate from its exact
`release/vX.Y.Z` branch. Tag publication revalidates that the same commit is on
`main` and referenced by an annotated matching tag before external publication.
Project release, portable installer, and OpenCode compatibility use separate
authorities. User documentation follows stable channels, while automation,
lockfiles, generated commands, and release artifacts retain checked exact values.
