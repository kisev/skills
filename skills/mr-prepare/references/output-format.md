# MR update output

Use the selected `en` or `ru` locale for chat, headings, status text, explanations
and publication prose. Default to English for an invocation and target without
language context. Preserve exact commands, API fields, paths, label names and
quotations. Required project-template markers remain unchanged.

After successful finalize, print the scaffold's `chat` field verbatim. The
stable path is an absolute filesystem path in inline code, not a Markdown link
or a `file://` URL. Do not print private evidence refs or an old successful plan
when the current attempt failed. Explain blockers in the selected language.

The stable `<artifact-root>/mr-publication.md` contains:

1. MR link and one manual-only notice.
2. TL;DR of proposed metadata edits and why they help.
3. Proposed title with its command, or a short unchanged notice.
4. Full proposed description with its command, or a short unchanged notice.
5. Only label add/remove delta, reasons and its command.
6. Observed checks, material limitations and the exact freshness-check command.

Do not show previous title/description, repeated current/proposed label lists,
raw SHAs, digests, internal bookkeeping or exhaustive assessment tables. Those
remain in private JSON. A freshness check is not a certification of prose quality.

Each command belongs beside its action. The runner generates directly runnable
`glab api` commands with explicit host/project/MR and immutable JSON request
files. Preserve their exact text. Their payloads must match the visible previews.
There are no commands for unchanged fields. Label requests contain only add/remove
delta, never an overwrite of unrelated labels. Nothing is executed by the skill.
The generated freshness command includes an expected binding. Preserve it so an
older open document cannot validate a newer replacement plan by mistake.

Successful generation replaces the stable document and its pointer under a
target-scoped lock with rollback. Old immutable plans and request files remain
bound to their own content. A failed generation must not advertise an older plan
as its result. Superseded plans require fresh preparation before publication.
