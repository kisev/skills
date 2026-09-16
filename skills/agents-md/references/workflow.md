# AGENTS.md Workflow

Treat create, update, reduce, and audit as composable parts of one
reconcile-and-validate workflow rather than mutually exclusive modes.

## Resources

Always read `references/agents-md-guidelines.md` before updating. It contains the
standard shared section and fact-collection checklist. It is a self-contained
skill resource; do not look for it in the working repository. Apply
`references/language-policy.md` to all user-facing prose.

## Algorithm

1. Determine the Git worktree root and the target scope directory.
2. Find all applicable `AGENTS.md` from the root to the target and nested files
   whenever their parent scope changes.
3. Create the root file when no applicable file exists.
4. Treat the local checkout, including uncommitted changes, as the source of
   truth. If only a remote repository is available, use its hosting tools to read
   files from the exact requested revision without producing remote effects.
5. Collect facts adaptively from manifests and task configuration, CI, tests,
   README/CONTRIBUTING, entry points, and analogous implementation files.
6. For every proposed rule, maintain a private `rule -> source` map. Do not print
   it in `AGENTS.md` unless the user requests it.
7. Distinguish inherited shared rules from scope rules. Do not duplicate parent
   instructions in a nested file.
8. Restore the shared section from the reference if it is missing or damaged. Do
   not change its meaning without an explicit request to change the shared rule.
9. Keep project rules to at most 20 one-line bullets without subsections. Retain
   only rules that prevent frequent errors or specify a non-obvious command or
   boundary.
10. Add only verifiable commands, paths, versions, CI behavior, environment
    variables, and ownership constraints. Include branch, merge/pull-request, and
    deployment rules only when current repository configuration or canonical
    documentation confirms them.
11. Remove stale, unconfirmed, and exact inherited duplicates. Do not replace
    user refinements with the template unless they conflict with repository facts.
12. Preserve the language established by existing repository instructions. Do
    not translate confirmed instructions solely to match the response language.
13. Before writing, recheck every new or changed rule against the source map and
    assess conflicts with parent and nested files.
14. Write the bounded project file directly with atomic replacement, then show
    the resulting diff.
15. Validate content, nesting, and scope after writing: the file exists when
    required, contains only applicable rules, has no stale or inherited
    duplicates, and does not conflict with nested files. If reconciliation
    produces no diff, report that the file is current.

## Result

- `AGENTS.md` is created or updated in the correct scope.
- The chat briefly lists changes, sources used, retained or removed rules, and
  unconfirmed constraints.
- Inheritance and conflicts with neighboring `AGENTS.md` have been checked.
