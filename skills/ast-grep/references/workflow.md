# Structural Search and Rewrite

Use AST search when node boundaries and metavariables matter; use text search when plain text is simpler. ast-grep patterns use `$NAME` for one node, `$$$NAME` for a node sequence, and repeated metavariables must match. The external CLI is not installed by this skill. `python3 -I -S -B scripts/ast_grep.py --capabilities` reports availability; a missing binary returns JSON `escalate` and must not trigger installation.

For read-only search run `python3 -I -S -B scripts/ast_grep.py search --pattern 'const $A = $B' --lang javascript PATH`. Report structured matches: file, range, matched text, and metavariables. Do not modify files or suggest apply for a search-only request.

Rewrite targets must be regular non-symlink files inside an existing non-symlink workspace. Always preview first with `python3 -I -S -B scripts/ast_grep.py rewrite --pattern 'const $A = $B' --rewrite 'let $A = $B' --lang javascript --workspace PATH PATH`. Report affected files, match count, diff, and `confirmation` digest. Zero matches are a no-op without confirmation. Add no `--apply` before explicit confirmation; afterward repeat exactly the same invocation with `--apply --confirm <DIGEST>`. The runner rebuilds the preview and rejects a different digest, stale target, traversal, and symlink before writing. It prepares every file before the first replacement and rolls back replaced files after a replacement error.

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

Rewrite targets must be regular non-symlink files inside an existing non-symlink workspace. Always create a preview first:

```shell
python3 -I -S -B scripts/ast_grep.py rewrite \
  --pattern 'const $A = $B' --rewrite 'let $A = $B' \
  --lang javascript --workspace PATH PATH
```

Show affected files, match count, diff, and the `confirmation` digest. On zero matches, report a no-op without confirmation. Do not add `--apply` before explicit user confirmation. After confirmation, repeat the exact same invocation with `--apply --confirm <DIGEST>`. The runner rebuilds the preview, rejects a different digest, stale target, traversal, and symlink without writing; preparation of all files finishes before the first replacement, and a replacement error rolls back already replaced files.
