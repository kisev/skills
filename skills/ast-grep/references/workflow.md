# Structural Search and Rewrite

Use AST search when node boundaries and metavariables matter; use text search when plain text is simpler. ast-grep patterns use `$NAME` for one node, `$$$NAME` for a node sequence, and repeated metavariables must match. The external CLI is not installed by this skill. `python3 -I -S -B scripts/ast_grep.py --capabilities` reports availability; a missing binary returns JSON `escalate` and must not trigger installation.

For read-only search run `python3 -I -S -B scripts/ast_grep.py search --pattern 'const $A = $B' --lang javascript PATH`. Report structured matches: file, range, matched text, and metavariables. Do not modify files or suggest apply for a search-only request.

Rewrite targets must be regular non-symlink files inside an existing non-symlink workspace. Run `python3 -I -S -B scripts/ast_grep.py rewrite --pattern 'const $A = $B' --rewrite 'let $A = $B' --lang javascript --workspace PATH PATH`; it validates all targets, writes immediately, and reports affected files, match count, and the resulting diff. Zero matches are a no-op. Use `--dry-run` only when the user explicitly asks not to write. The runner rejects changed targets, traversal, and symlinks before writing, prepares every file before the first replacement, and rolls back replaced files after a replacement error.

Use AST search instead of text search when node boundaries and metavariables matter. For plain text, text search is faster and clearer. Patterns use ast-grep syntax: `$NAME` is one node, `$$$NAME` is a sequence of nodes, and repeated metavariables must match.

This skill does not install the external CLI. `python3 -I -S -B scripts/ast_grep.py --capabilities` reports its actual availability. If the binary is absent, the runner returns JSON `escalate`. Do not install it automatically.

## Search

From the skill directory, perform read-only search only:

```shell
python3 -I -S -B scripts/ast_grep.py search \
  --pattern 'const $A = $B' --lang javascript PATH
```

Show structured matches: file, range, matched text, and metavariables. Do not modify files or propose apply when the user requested search only.

## Rewrite

Rewrite targets must be regular non-symlink files inside an existing non-symlink workspace:

```shell
python3 -I -S -B scripts/ast_grep.py rewrite \
  --pattern 'const $A = $B' --rewrite 'let $A = $B' \
  --lang javascript --workspace PATH PATH
```

The command writes immediately and returns affected files, match count, and the resulting diff. On zero matches, report a no-op. Use `--dry-run` only for an explicitly requested read-only run. The runner rejects changed targets, traversal, and symlinks without writing; preparation of all files finishes before the first replacement, and a replacement error rolls back already replaced files.
