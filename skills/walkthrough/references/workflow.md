# Workflow

The skill only reads the checkout and is not a review. Do not change files, issue
a verdict, or suggest approval. Use a separate review workflow to evaluate quality
after the walkthrough.

## Runner

Run from the skill directory:

```shell
python3 -I -S -B scripts/walkthrough.py \
  --repo-root <REPO_ROOT> [--range <BASE..HEAD> | --diff-file <DIFF_FILE>] \
  [--chunk-size 8] [--chunk-index <INDEX>]
```

Without `--range` and `--diff-file`, the runner includes staged, unstaged, and
untracked changes relative to `HEAD`. For a range, use the exact Git range. For a
ready diff file, provide the already obtained artifact and do not collect another
diff. `--capabilities` only reads Git availability.

The runner JSON is evidence: do not recalculate statistics or relationships
manually. With multiple chunks, first read `chunk_manifest`, then request every
`--chunk-index` sequentially. A partial result has `coverage.complete=false` and
`uncovered_files`; explicitly show the uncovered part and do not call that chunk
the full diff.

## Narrative from the result

Return numbered steps in the order `contracts -> logic -> tests -> configs`.
Every changed file must belong to exactly one step. For every step, specify the
files, intent from the diff, what to read next, and exact links from
`relationships`. Separately show `attention` with migration, permissions, and
deleted files. Finish with an explicit boundary: this is a reading map, not an
evaluation of change quality.
