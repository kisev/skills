# safe-fs

[Русская версия](README.ru.md)

`@kisev/safe-fs` holds the shared filesystem safety primitives used by the
kisev agent packages: `writeAtomic` for private single-link atomic replacement,
`readRegular` for reading regular files only, `assertSafePath` for
symlink-free traversal, and the `LifecycleError` failure type.

## Install

```bash
npm install @kisev/safe-fs
```

Every write goes through an exclusive temporary file with `fsync`, a mode
restriction, and a directory sync, and rejects symlinks, multi-link files, and
non-directory parents.
