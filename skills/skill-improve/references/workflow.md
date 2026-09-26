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

## Session evidence

Ground the improvement in real usage with the read-only session report:

```shell
python3 -I -S -B scripts/skill_improver.py sessions [--skill NAME] [--host HOST]
  [--db PATH] [--since DAYS] [--limit N] [--min-pattern-count N]
```

The command reads opencode, kilo, and mimo session databases strictly
read-only. `--host auto` discovers `opencode.db`, `kilo.db`, and `mimocode.db`
in the XDG data directory; `--db` points at any compatible SQLite database. The
output is one JSON value with deterministic signals only: per-skill invocations,
status counts, durations, verbatim error excerpts, retry sessions, the first
user message after each invocation, frequent actions, recurring action pairs
between skill invocations, and new-skill candidates.

- Interpret the signals semantically. Errors, retries, and follow-up user
  messages are signals of possible problems, not findings by themselves.
- Treat `candidates` as evidence, not decisions: propose a new skill or an
  improvement only when a pattern recurs across sessions and has a concrete
  improvement it would produce.
- Session excerpts are verbatim and confidential: never copy them into
  persisted files, the eval corpus, commit messages, or published text.
- A missing database, empty history, or a `--skill` filter without invocations
  is a valid outcome; it must not block the static check cycle.

## Cycle

1. Run `check` for one target and read the JSON. The absence of real successful
   or unsuccessful sessions is allowed and must not block the check.
2. Before the first write, identify the critical and major findings and exact
   paths. Keep every edit inside the selected skill and write project files
   directly with atomic replacement or rollback.
3. Fix the causes of critical and major findings without rewriting the skill for
   style. When real session examples are available, collect only the minimum
   needed evidence and anonymize prompts, paths, identifiers, credentials, and
   logs before using them.
4. Assess every minor finding separately and skip a false positive with a brief
   reason.
5. Repeat `check` until exit code `0`. After edits, run the available checks for
   the target skill. Add a durable example to the eval corpus only as a separate,
   explicitly reviewed and verified change; never make the corpus depend on
   session availability.
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
