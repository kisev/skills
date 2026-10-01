# safe-fs

[Русская версия](README.ru.md)

`@kisev/safe-fs` holds the shared filesystem safety primitives used by the
kisev agent packages: `writeAtomic` for private single-link atomic replacement,
`readRegular` for reading regular files only, `assertSafePath` for
symlink-free traversal, and the `LifecycleError` failure type.

## Install

```bash
# Registry version
npm view --prefer-online @kisev/safe-fs@latest version

# Install in this npm project
npm install @kisev/safe-fs

# Installed dependency
npm list @kisev/safe-fs --depth=0
```

The tag can move between preview and installation; `npm list` reports the
dependency actually installed in this project. This library has no CLI.

Every write goes through an exclusive temporary file with `fsync`, a mode
restriction, and a directory sync, and rejects symlinks, multi-link files, and
non-directory parents.
