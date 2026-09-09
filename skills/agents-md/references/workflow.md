# AGENTS.md Workflow

Read `references/agents-md-guidelines.md`; it is a self-contained skill resource, not a file to locate in the target repository. Determine the Git worktree root and target scope. Find every applicable `AGENTS.md` from the root to the target and nested files whenever their parent scope changes. Create the root file when no applicable file exists.

Collect facts adaptively from manifests and task configuration, CI, tests, README/CONTRIBUTING, entry points, and analogous implementation files. Keep a private `rule -> source` map for every proposed rule. Distinguish inherited general rules from scope rules and never duplicate parent instructions in a nested file. Restore the reference general block if absent or corrupted; do not change its meaning without an explicit request.

Keep project rules to at most 20 one-line bullets with no subsections. Include only verified commands, paths, versions, CI behavior, environment variables, ownership limits, frequent-error prevention, or a non-obvious command or boundary. Remove stale, unverified, and exact inherited duplicates, but do not replace user refinements with a template unless facts contradict them. Create, update, reduce, and check are composable parts of one reconcile-and-validate run, not mutually exclusive modes. Recheck each proposed rule against its source map and parent/nested conflicts. Show the exact diff and obtain explicit confirmation before applying only the agreed change.

Report the correct-scope file, sources used, retained or removed rules, unverified limits, and the checked inheritance/conflicts.

## Resource

Always read `references/agents-md-guidelines.md` before updating. It contains the canonical common block, a fact-collection checklist, and the minimal structure. It is a self-contained skill resource; do not look for it in the working repository.

## Algorithm

1. Determine the Git worktree root and the target scope directory.
2. Find all applicable `AGENTS.md` from the root to the target, as well as nested files if their parent scope changes; if none applies, plan the root `AGENTS.md`.
3. Collect facts adaptively: manifests and task configuration, CI, tests, README/CONTRIBUTING, entry points, and several analogous implementation files.
4. For every proposed rule, maintain a `rule -> source` map. Do not print it in `AGENTS.md` unless the user requests it.
5. Distinguish inherited common rules from scope rules. Do not duplicate parent instructions in a nested file.
6. Restore the common block from the reference if it is missing or damaged. Do not change its meaning without an explicit request to change the common rule.
7. Keep project rules to at most 20 single-line items without subsections. Retain only rules that prevent frequent errors or specify a non-obvious command or boundary.
8. Add only verifiable commands, paths, versions, CI behavior, environment variables, and ownership constraints.
9. Remove stale, unconfirmed, and exact duplicate inherited rules. Do not replace user refinements with the template unless they conflict with facts.
10. Before writing, recheck every new rule against the source map and assess conflicts with parent and nested files.
11. Show the exact diff and obtain explicit confirmation before writing. After confirmation, apply only the agreed change.
12. Validate content, nesting, and scope after writing: the file exists when required, contains only applicable rules, has no stale or inherited duplicates, and does not conflict with nested files. If reconciliation produces no diff, report that the file is current.

## Result

- `AGENTS.md` is created or updated in the correct scope.
- The chat briefly lists changes, sources used, retained or removed rules, and unconfirmed constraints.
- Inheritance and conflicts with neighboring `AGENTS.md` have been checked.
