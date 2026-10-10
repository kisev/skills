# Mattermost Workflow

## Runner

Invoke `scripts/mattermost.py` relative to this `SKILL.md` with the installed
Python interpreter. The runner is stdlib-only; do not install packages or create
an environment.

```shell
python '/path/to/mattermost/scripts/mattermost.py' read 'MATTERMOST_URL'
```

Use `read-many` for several explicit URLs and `members` only when the user asks
for channel or chat membership. `--since` and `--until` accept timezone-aware
ISO-8601 timestamps and apply only to channels and chats. Their interval is
start-inclusive and end-exclusive. The default starts at the user's local
midnight and ends at the current time.

`--timeout SECONDS` bounds every GET request; the default is 60 seconds and
values above 600 are rejected. `read-many` continues past a source whose
request times out: that target is returned with error code `network_timeout`
and `retryable=true`, while the remaining URLs are still read. Re-run the
exact URL to resume it from the coverage cache instead of repeating the bulk
export.

For long `read` results, use `--view transcript` to display posts in chronological
windows without emitting their bulky API metadata. The default window contains
10 posts; `--offset N --limit N` selects another window, with a limit of 1 to 50.
Follow `window.next_offset` until it is `null`, keeping the exact URL and period
unchanged. The first chat or channel transcript read freezes the current time in
`period.until`; pass its exact `period.since` and `period.until` as `--since` and
`--until` for every later window. For a
post thread, or if posts are edited during paging, windows are not a durable
snapshot: recheck the IDs and coverage before claiming an exhaustive transcript.
Each response retains the read status, coverage, counts, warnings,
errors, and cache facts. `complete` describes the fetched interval, not how many
windows have been displayed; use `window.total` and `window.returned` for that.
Plain `read` still returns the full JSON result, and the view never truncates a
post's message. If a single message exceeds the host output limit, inspect its
saved output instead of interpreting a truncated excerpt as the complete text.

Reactions are fetched by default through separate GET requests and returned as
exact `{emoji, user}` pairs; `references/runner-contract.md` owns the
null-reactions and approval rules. Use `--no-reactions` only when the user asks to omit
them, or on Band origins: Band, a Mattermost fork, does not serve the reactions
API, so reads there run with `--no-reactions` instead of collecting per-post
failures.

## Scope

Resolve only an exact HTTPS URL supplied by the user or the exact Mattermost URL
in the current host context. Mattermost URLs already encode names in their exact
channel, direct-message, group, and permalink routes. Mattermost-compatible fork
origins, such as Band, use the same routes and are in scope on their own exact
origins. If the context is absent or ambiguous, ask for the exact URL.

Reading and publication preparation follow `references/runner-contract.md`:
requests are GET-only and remain at the selected origin; only the separately and manually invoked
publication helper sends the bounded POST requests described below.
Attachment files are completely excluded from reading.

A post ID in a URL takes precedence over its channel path and reads that post's
whole thread. A channel or chat URL reads only posts
created in the requested period. If an in-period reply has an older root, fetch
only that root and mark it `context_only`; do not load the rest of the old thread.
Resolve direct and group chats only from the URL's exact username, channel ID, or
direct-channel name. Do not broaden resolution into search.

For direct chats, `identity.self_id` and `identity.peer_id` come from the
authenticated account and the validated direct-channel name. A verified
`@username` URL also supplies `identity.peer_username`. The transcript labels
only these IDs as `self` or `peer`; all other authors are `unverified` and retain
their exact `user_id`. Do not infer authors from ID prefixes, channel ordering,
or group membership. `created_at_utc` is explicitly in UTC; use one timezone for
all date filtering rather than mixing local time with a different UTC offset.

## Cache

The SQLite cache is one private `cache.sqlite3` under the user's XDG cache home
in a `mattermost/` directory, isolated by normalized origin and current user ID.
Access to the exact post or channel is revalidated before every cache read.

- Coverage newer than seven days is reusable for 300 seconds.
- Coverage wholly older than seven days is intentionally treated as immutable
  and stable, with no freshness expiry. This is a deliberate
  performance/freshness tradeoff that avoids repeated historical API reads;
  late edits and deletes are not observed unless the caller uses `--refresh`.
- One read whose interval crosses the seven-day boundary is split into a stable
  segment and a fresh segment; each segment follows its own rule above.
- Thread composition is reusable for 300 seconds.
- Reactions are never cached and are fetched again unless `--no-reactions` is set.
- Partial reads may cache individual posts but never mark an interval or thread
  complete.
- `--refresh` bypasses cache reads and replaces successfully fetched coverage.
- `--no-cache` does not open or modify the cache.
- Cache corruption, unsafe paths, I/O errors, or unsupported schemas stop the
  operation with `cache_error`; do not silently continue through the API.

Stable cache can therefore retain and return content that was later edited or
deleted, including for security or compliance reasons. Use `--refresh` whenever
the current redaction or deletion state matters.

Inspect the cache with:

```shell
python '/path/to/mattermost/scripts/mattermost.py' cache status
```

`cache clear` is a confirmed two-step local mutation. Run it without `--confirm`,
then repeat the emitted `apply_command` only after user approval.

## Authentication and publication stages

At the authentication stage (exit code `3`,
`authentication_required`) and at the publication stage (a send request), read
`references/authentication-and-publication.md`: it owns the credential flows,
the manual publication plan, and the opt-in Issue/MR card mode. This file keeps
the read-only scope, cache, and result contracts.

## Result Contract

Read JSON from stdout. Check `status`, `complete`, `scope`, `period`, `counts`,
`pages`, `errors`, `warnings`, `cache_hit`, `cache_age`, and
`access_revalidated` before using `posts` or `members`, including transcript
windows. A successful empty period is `status=ok`, `complete=true`, and
`posts=[]`; `references/runner-contract.md` owns the partial-evidence rule. A
`network_timeout` error is retryable and covers
only the affected target; other targets in the same `read-many` result are
unaffected.

Exit codes are `0` for complete success, `1` for a partial result, `2` for input
or target errors, `3` for required authentication, and `4` for cache errors.
Default read output is a read-only result in chat. Publication preparation has no
external mutation and stops with a manual plan. Only the separate helper can
upload files and create one post per digest-confirmed command; edit, delete,
reaction, channel, and member mutations are unsupported.
