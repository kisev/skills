# Workflow

## Boundary

- Run only on an explicit user request. Session diagnosis, source matching, and
  the bug-report archive are three separate requests; never chain them and never
  start any of them from other activity.
- Do not audit a skill without session history: doctor diagnoses real usage, it
  is not a static checker. Do not apply automatic fixes, do not modify skill
  sources, and do not connect this skill to `stopit` or any handoff flow.
- All state lives under the private XDG state root
  `$XDG_STATE_HOME/agent-skills/skill-doctor/` (the bundled runner resolves the
  platform default when the variable is unset). Diagnoses and report archives
  stay there; nothing is sent anywhere, and transfer of a finished archive is
  manual.

## Current-session evidence

Ground every diagnosis in the current session only. Ask the host for the
current session identifier, then run the read-only collector from the skill
directory:

```shell
python3 -I -S -B scripts/skill_doctor.py collect --session-id <SESSION_ID> \
  [--host opencode|kilo|mimo|auto] [--db <PATH>] \
  [--max-actions N] [--max-messages N] [--max-excerpt-chars N]
```

- The collector reads opencode, kilo, and mimo session databases strictly
  read-only and reports only the session with the exact given identifier. If
  the identifier cannot be established reliably, or no database contains that
  session, stop the diagnosis and report the reason. Never substitute another
  session and never guess an identifier.
- The output is one JSON value: session facts, a `coverage` block
  (`complete`, `truncated`, explicit `notes`), skill invocations with statuses,
  errors, and durations, user messages, and the bounded action timeline.
- Interpret the collected items semantically. Errors, retries, and follow-up
  user messages are evidence of possible problems, never findings by themselves.
- Session excerpts are verbatim and confidential: keep them only in private
  XDG state, never in the repository, eval corpus, commit messages, or any
  published text.

## Diagnosis record

Validate the structure against `references/diagnosis.schema.json` while
authoring. Store the result through the runner; never write XDG state manually:

```shell
python3 -I -S -B scripts/skill_doctor.py show --session-id <SESSION_ID> --host <HOST>
python3 -I -S -B scripts/skill_doctor.py record --session-id <SESSION_ID> --host <HOST>
```

`record` reads the complete diagnosis JSON from standard input, validates it,
and keeps one record per session under
`sessions/<key>/diagnosis.json`; different sessions never overwrite each other.

Authoring rules:

- Classify every observation as `skill-defect`, `environment`, or
  `agent-execution`, and mark it `suspected` or `confirmed`. Present a cause as
  confirmed only when recorded evidence supports it; suspected causes stay
  labeled as hypotheses with what would confirm them.
- Cite evidence identifiers for every observation. Record code fingerprints
  (exact identifiers, rule names, error substrings from the skill's sources)
  for every skill defect; they are what later matching verifies.
- Separate `conclusions` from `open_questions`. Write concrete proposals, and a
  known `workaround` when one was observed.

Incremental rules enforced by the runner:

- Before recording, run `show` and merge: keep observation identifiers stable,
  add new evidence, and revise conclusions instead of duplicating them.
- Evidence is append-only; recorded evidence entries must not be dropped or
  rewritten. The runner archives the previous version into a content-addressed
  history and reports `added`, `revised`, and `retained` counts.

## Development use in a skill repository

When doctor is explicitly invoked inside a repository that carries skill
sources, search the XDG state for applicable diagnoses, including diagnoses
recorded in other working projects, and match them against the current
sources:

```shell
python3 -I -S -B scripts/skill_doctor.py match --skills-root <SKILLS_DIR>
```

- Matching is read-only. For every recorded skill-defect observation it
  compares the recorded declared origin (the skill's source URL) or local root
  with the current source and checks every code fingerprint.
- Report which problems are `relevant`, `resolved`, `unclear`, or
  `needs-clarification`, with reasons. A matching skill name alone is
  insufficient: when the recorded origin is unknown, local to another tree, or
  differs from the current declared source, the verdict is
  `needs-clarification`, never a confirmed match.
- The ordinary result is analysis and proposals for the user; doctor does not
  modify skill sources in this mode.

## Public bug report

Prepare an archive only on a separate explicit request, after the diagnosis is
recorded. Author the already anonymized content: identification of the skill
(name, declared source, version or an explicit unknown), expected and actual
behavior, a minimal example that reproduces the problem without private data,
the known workaround, and recommendations. Apply `humanize` to the authored
prose and keep the section names, technical identifiers, and redaction
contract exact. Never include conversation history,
raw session logs, project files, private diagnosis records, or the
anonymization mapping, and keep the sections `## Identification`,
`## Expected behavior`, `## Actual behavior`, `## Minimal example`,
`## Workaround`, and `## Recommendation`.

Preview, then write after explicit confirmation:

```shell
python3 -I -S -B scripts/skill_doctor.py report prepare --skill <NAME> \
  [--session-id <SESSION_ID>] [--forbid-value VALUE ...] [--forbid-file <PATH>]
python3 -I -S -B scripts/skill_doctor.py report commit --skill <NAME> \
  --expected-dir <CONFIRMED_DIR> [same redaction flags]
```

- Pass the request JSON on standard input (`schema`
  `agent-skills/skill-doctor/report-request/v1` with `skill`, `source`,
  `version`, `reproduction`, `created_at`, `report_md`, `example_files`).
  Mark an unknown version as `null` and unverified reproduction as
  `unverified`; the manifest marks both explicitly.
- `prepare` is read-only: it shows the exact destination, every file with its
  full content and digest, the exclusion list, and the anonymization notes.
  Show this preview completely and obtain explicit confirmation.
- Pass every private value (session identifier, workspace paths, hostnames,
  replacement values of the anonymization) through the redaction flags; the
  runner refuses to prepare or write an archive that contains any of them, in
  content or in file names.
- `commit` accepts only the exact previewed destination through
  `--expected-dir`, writes the identical files with private permissions and
  neutralized file timestamps, and refuses to change an existing archive.
- Pass the exact approved content again on standard input; do not create a
  draft artifact. Handing over the archive to an issue tracker stays a manual
  user action.

## Result

- The current session's difficulties, errors, interventions, workarounds, and
  outcomes are recorded with evidence, causes, and proposals in private state,
  revisable without duplicates.
- Development invocations report which known problems still apply to the
  current sources, with ambiguous provenance kept explicitly unresolved.
- A public archive exists only after preview and confirmation, is
  self-contained, and matches its preview exactly.
