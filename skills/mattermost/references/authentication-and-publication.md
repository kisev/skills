# Authentication and publication

This file owns the two credential-bearing stages of the mattermost skill:
origin-bound authentication for reads, and manual publication preparation.
`workflow.md` routes here at these stages; the cache, scope, and result
contracts stay there.

## Authentication

Run `read` first. Exit code `3` and error code `authentication_required` mean an
origin-bound credential is missing or expired. Do not ask for credentials in
chat, print them, or pass a token through argv. Ask the user to choose one of two
modes; recommend the browser flow.

### Browser flow

1. Prepare an exact-origin preview with `python
   '/path/to/mattermost/scripts/mattermost.py' auth preview 'MATTERMOST_URL'`.
2. Present the preview and request explicit consent. Do not treat the original
   read or send request as consent to change authentication state.
3. After consent, run the emitted apply command with `--browser-consent`. The
   runner opens only the exact HTTPS origin through installed `agent-browser`,
   obtains the origin-bound session without exposing it in chat, and validates it
   against that origin's `/api/v4/users/me` before saving it.
4. Repeat the original operation once. If exit code `3` remains, stop and report
   that browser authentication did not produce an origin-bound session.

### Manual token file

Run `python '/path/to/mattermost/scripts/mattermost.py' auth path
'MATTERMOST_URL'` to obtain the exact origin-bound `token_path`. The user must
create its directories as owner-only real directories with mode `0700`, then
write the raw token followed by one newline to a regular, owner-owned,
singly-linked file at that path with mode `0600`. The token must never enter
argv, chat, logs, or a command shown by the skill. Repeat the original operation
after the user confirms that the file is ready.

## Publication

A send request selects this skill. Prepare a manual publication plan, but never
invoke a generated publication `apply` or `inspect` command, even when the user
asks the agent to send automatically. Editing or deleting posts, changing
reactions, channels, or members, and other Mattermost mutations remain excluded.

Pass one JSON object on stdin to the preparation command:

```shell
python '/path/to/mattermost/scripts/mattermost.py' publication prepare <<'JSON'
{"messages":[{"target":"https://mattermost.example/team/channels/channel","message":"Prepared message","files":[]}]}
JSON
```

The object contains only a non-empty `messages` array. Each ordinary item contains
exactly `target`, `message`, and `files`. Every target is an exact supported HTTPS
Mattermost URL, and all targets in one plan use one origin and authenticated
identity. `files` contains zero to five normalized absolute source paths. Each
source must remain an owner-owned, singly-linked regular file of at most 100 MiB
with no symbolic-link path component. The runner records its size and SHA-256;
it does not copy source files. An empty message is valid only with at least one
file.

Preparation performs exact-target GET validation and writes a stable private XDG
plan at the returned `plan_path`. Its bodies, actions, and versioned plan history
are immutable. Present the plan, including each message body, target, file path,
size, digest, expiry, risks, and commands. Each message has its own action digest
and one separate digest-confirmed Apply command. One digest never confirms
several messages.

The user may manually invoke an Apply command. That one command is one compound,
user-visible publication action: it may upload zero to five files and then create
exactly one post. Immediately before POST, the helper revalidates the action,
identity, exact target, body digest, and every source file's metadata and digest.
The post carries hidden `props.agent_skill_publication_id` for exact recovery; do
not add a visible marker to its message.

Progress is durable across invocation failure. Never retry after an ambiguous
upload because Mattermost may retain an unattached server file. After an
ambiguous post, the user may manually run that message's Inspect command; it
checks for the hidden publication ID and exact post content. The skill never runs
Apply or Inspect and never claims an unknown outcome succeeded.

### Opt-in Issue and MR cards

Use card mode only when the user explicitly requests it or an applicable trusted
project/process instruction (such as `AGENTS.md`) selects it. A GitLab link alone
never selects card mode. Follow [the card guide](cards.md) for standard Issue/MR
templates, custom layouts, English/Russian examples, and compactness limits.

Add `card` to an item with `message: ""` and `files: []`. One card creates one
new thread root in the exact channel or chat, never a reply to an existing post.
The agent fills the card from supplied evidence; the runner does not fetch GitLab.
Use the requested language, otherwise the conversation language, with English
as the ambiguous-language fallback. Preserve source names and distinguish unknown
data from absent values. Do not infer Mattermost mentions from GitLab usernames.

Card validation failures stop preparation with localized, field-specific errors.
Revise the text or select fewer labels with an accurate omitted count and retry;
never bypass a budget error by switching to an ordinary message automatically.
Preparation stores card inputs and the rendered attachment in a version-2 action
covered by its confirmation digest; renderer drift requires a new plan;
ordinary actions remain version 1. Present the full rendered attachment from the
plan as well as the target, digest, expiry, and manual commands. The helper checks
card content during recovery, allowing only empty server-added attachment defaults.
It never invokes a generated command on the agent's behalf. Cron, subscriptions,
post edits, and automatic publication remain outside this workflow.
