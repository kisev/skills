# Build, Distribution, and Compatibility

Canonical definitions and shared files generate portable and OpenCode assets.
Generated outputs are checked for parity, reproducibility, and undeclared files.
Portable Pages archives are content-addressed and self-contained; the npm package
is an independent OpenCode adapter with peer range `>=1.18.29 <1.19.0`.
One release manifest binds every Pages file and the exact npm tarball to the tag
and revision. Publication verifies both remote channels before creating the
GitHub Release. Compatibility checks are pinned, hostless where possible, and
no-network/no-secret.
