# Workflow

## Target boundary

The skill accepts exactly one existing directory containing `SKILL.md`, or a path
to `SKILL.md` itself. Check multiple skills in separate runs. Do not search for
skills in global directories or choose a target by guesswork: when no path is
provided, ask one clarifying question.

Run the read-only checker from the skill directory:

```shell
python3 -I -S -B scripts/skill_improver.py check --path <SKILL_DIR>
```

The runner outputs one JSON value. Exit code `0` means no critical or major
findings, `1` means there is a critical or major finding, and `2` means a usage
error. `--capabilities` has no side effects.

## Cycle

1. Run `check` for one target and read the JSON.
2. Before the first write, show the critical and major findings, exact paths, and
   planned diff; obtain confirmation.
3. Fix the causes of critical and major findings without rewriting the skill for
   style.
4. Assess every minor finding separately and skip a false positive with a brief
   reason.
5. Repeat `check` until exit code `0`. After edits, run the available checks for
   the target skill.
6. Only with a clean result, finish with a separate line
   `<skill-improvement-complete>`. Before it, list deliberately skipped minor
   findings with their reasons.

## Checker severity

- `critical`: missing or invalid frontmatter, invalid name, name and directory
  mismatch, missing description, unsafe or broken resource path, or a declared
  missing script.
- `major`: description too long, unsupported frontmatter field, a script without
  working `--help`, or `SKILL.md` longer than 500 lines without `references/` for
  progressive disclosure.
- `minor`: an unclosed TODO or FIXME.

The checker validates Agent Skills, not commands, plugins, agents, or tools of a
specific host.
