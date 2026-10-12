# Session modes and argument resolution (auto / manual)

Every remote review session resolves five arguments from the user's request
line (decision 75): `mr=<exact merge request URL>`, `mode=auto|manual`,
`fix=none|suggestion|patch`, `locale=en|ru`, and `profile=<name>`. The free
text left after the arguments is review context, never another argument.
Parse the arguments first; then resolve what is missing by mode.

## Auto mode

Auto is the findings-only mode: the pipeline, critics, and arbitration run on
the profile defaults, and the runbook carries findings as comments without
suggestions or Git patches plus one ready metadata proposal comment (SemVer,
labels, title, description, milestone) — not per-item commands; publication
stays manual and `publish=auto` does not exist in this wave. Any argument the
request leaves unset is a hard stop: print exactly which argument is missing
and how to pass it (`mode=auto mr=<url> fix=none locale=en profile=<name>`),
never assume a value. A missing profile stops the same way with the
`profile-setup` instruction; auto cannot run on guesses. Auto forces
`fix=none` — pass `--session-mode auto --fix-policy none` to `reviewmatic run`
(or `prepare`), which the runtime itself enforces.

## Manual mode

Manual is the interactive mode. When the request carries data without
explicit arguments (a bare MR link, free text), build your recommendations
for every unresolved argument and confirm them all in one question round —
one round for all arguments together, never one question per argument. With
nothing provided at all, ask the profile question per the question doctrine
(`references/question-guidelines.md`): questions are dependency-bounded, so
dependent questions are never grouped and a list option bundles only
independent choices. A missing profile in manual mode is one poll question,
and a confirmed answer may be saved explicitly by a separate
`profile=setup` invocation - never save silently. Mandatory simple questions
follow the findings: confirm each finding, ask fix-or-remark, and collect
extra details; a rejected finding is never authored further. Whatever the
agent can decide from evidence is never asked. The user may escape with
«дальше без вопросов» / "continue without questions" at any moment: the
remaining arguments take the profile defaults (or the documented defaults
without a profile) and the final report notes which arguments were resolved
that way.

## Profiles

A profile stores the session defaults — `locale`, `fix_policy`, `review_mode`,
and the recorded panel selection for the critic poll. It is written only by an
explicit setup invocation, never as a side effect of a confirmed manual round:

```shell
reviewmatic profile-setup --name work --locale ru --fix-policy none --review-mode normal --participants <selection.json>
reviewmatic profile-show --name work
```

(Run every command through the pinned `uvx --from "$REVIEWMATIC_FROM"`
wrapper the entrypoint establishes.)

Read a profile with `profile-show` before resolving arguments; a `missing`
status carries the setup instruction verbatim. The profile file lives under
`${XDG_CONFIG_HOME:-~/.config}/agent-skills/code-review/profiles/<name>.json`
and is owned by the runtime - never edit it by hand. When a stored panel
selection exists, pass its selection JSON to `reviewmatic run --participants`
so the poll is answered from the profile; without a stored selection an auto
session stops (the poll is a user question) and a manual session asks it.

## Thread matrix (decision 75.5)

| Thread state | Review result | Outcome |
| - | - | - |
| resolved | no problem | `no_reply` |
| resolved | same or related problem | `reply` + `reopen` (+ suggestion when the fix policy asks) |
| open | fixed | `reply` + `resolve` |
| open | confirmed, no fix attempted | `no_reply` |
| open | not fixed, fix attempted | `reply` (+ suggestion when the fix policy asks) |
| open | not confirmed | `reply` + `resolve` |

`no_reply` replaced `no_publication` everywhere. Every published answer opens
with its Conventional Comments label; the runtime refuses an unlabeled one.
