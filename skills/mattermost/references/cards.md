# Compact Issue and MR cards

Use this opt-in format for the opening post of a discussion or review thread.
It uses legacy Mattermost attachments, not Blocks or a server plugin. The
publication runner accepts one `card` per message with an empty `message` and
`files` array; use a channel/chat URL rather than a post permalink.
See [publication](workflow.md#publication) for authentication, exact-target
validation, immutable plans, expiry, manual Apply/Inspect, and recovery rules.

## Contract

Every card requires `kind` (`issue` or `mr`), `template` (`standard` or `custom`),
`locale` (`en` or `ru`), `title`, `url`, and `summary`.

- Put the project reference and concise object title in `title`. `url` is its
  absolute credential-free HTTPS GitLab URL; the title becomes a link.
- Write `summary` from evidence: the problem/proposed change or the MR's effect.
  Include a review focus only when known. Never invent a request or a status.
- All text inputs are plain text, not Markdown. The renderer escapes Markdown
  and mentions to keep pasted descriptions from adding images, headings, or pings.
  Custom formatting consists of ordering named fields and choosing half/full width.
- Standard cards require `status`, `author`, `assignee`, `milestone`, `labels`,
  and `omitted_labels`. MR additionally requires `pipeline` and `approvals`.
  Author and assignee each have one display value in this workflow. Use `null`
  for unknown scalar metadata and `""` for confirmed absence; they render as
  `Unknown`/`None` or their Russian equivalents. Other scalar values are strings.
- `approvals` is a factual count string, such as `"1/2"` only when both received
  and required counts are known. Use `"1"` when only the received count is known,
  `"0"` for zero, and `null` for unknown. Do not equate passing CI with approval.
- `labels` contains the selected exact names; `[]` means none, `null` means
  unknown. `omitted_labels` is an integer from 0 to 10000, zero for unknown labels.
  Select important labels according to project/process rules or agent judgment;
  count the rest accurately. The renderer appends `N more` (localized) without
  silently dropping any supplied value. The title links to the full object.
- Custom cards replace all standard metadata keys with `fields`, an ordered
  array of `{title, value, short}` objects. Supply localized captions and text;
  `short: true` allows pairing with the next short field, `false` uses full width.
  Reuse standard semantics for unknowns and omitted labels when applicable.
- Source titles, names, labels, and milestone names are not translated. Translate
  authored summaries and status explanations to the selected locale. Built-in
  captions, absence markers, omitted counts, and card errors use that locale.
  Invalid/unsupported locale diagnostics fall back to English.

Unknown keys are rejected: arbitrary `props`, attachments, actions, images, HTML
layouts, and remote resources cannot be supplied. One neutral accent identifies
the object kind (blue Issue, purple MR); it does not imply success or severity.

## Compactness budget

These are conservative authoring limits, not a guarantee about every viewport:

| Input | Limit |
| - | - |
| Title | 100 characters, one line |
| Summary | 240 characters, at most three explicit lines and 8 estimated lines |
| Field caption / value | 28 / 100 characters, one line each |
| Custom fields | 8 |
| Selected labels | 10, combined display including omitted count at most 100 characters |
| Visible title + summary + captions + values | 1000 characters |
| Estimated layout | 28 lines |
| Object URL | 2048 characters |

Line estimation uses 40 character cells at full width and 20 at half width,
counts wide Unicode characters as two cells, and counts explicit line breaks.
Each field adds caption/value lines plus one spacing line. Consecutive short
fields share a row at the maximum of their heights. Title and summary add their
estimated lines. Control/format characters other than permitted newlines are
rejected. No renderer truncation or automatic trimming occurs.

When validation fails, shorten the named text, reduce custom fields, or explicitly
select fewer labels and update `omitted_labels`. Keep the purpose and important
facts; defer the rest to GitLab. Do not split a single object's root into several
cards automatically.

The Mattermost v10.10.0
[attachment renderer](https://github.com/mattermost/mattermost/blob/v10.10.0/webapp/channels/src/components/post_view/message_attachments/message_attachment/message_attachment.tsx)
wraps attachment `text` in `ShowMore` with `maxHeight={200}` and renders metadata
fields separately. This supports using a short summary plus bounded fields, but
does not establish the exact v10.10.19 client's behavior. Font, zoom, window
width, and thread panel affect wrapping. Target-instance verification is still
required: check both locales, normal channel view and narrow thread panel, long
typical titles, and near-budget cards. Record actual viewport/zoom and whether
the main content is visible without expansion. Do not claim a live check from
the estimator or mock API tests. Any test publication requires the user's exact
target/content approval and manual execution of its Apply command.

## Standard examples

Each JSON block below is the `card` value, not the complete publication request.
Names and metadata are illustrative fixtures, not fetched GitLab data.

### Issue, English

```json
{"kind":"issue","template":"standard","locale":"en","title":"api#123 · Duplicate notifications","url":"https://gitlab.example/team/api/-/issues/123","summary":"Retries send duplicate notifications. Discuss deduplication by event key.","status":"Open","author":"Alice","assignee":"Bob","milestone":"v1.2","labels":["bug","backend"],"omitted_labels":3}
```

### Issue, Russian

```json
{"kind":"issue","template":"standard","locale":"ru","title":"api#123 · Duplicate notifications","url":"https://gitlab.example/team/api/-/issues/123","summary":"Повторные запросы дублируют уведомления. Обсуждаем дедупликацию по ключу события.","status":"Открыта","author":"Alice","assignee":"Bob","milestone":"v1.2","labels":["bug","backend"],"omitted_labels":3}
```

### MR, English

```json
{"kind":"mr","template":"standard","locale":"en","title":"api!248 · Deduplicate notifications","url":"https://gitlab.example/team/api/-/merge_requests/248","summary":"Checks event keys before delivery. Review focus: concurrent retries.","status":"Ready for review","author":"Alice","assignee":"Bob","milestone":"v1.2","labels":["backend"],"omitted_labels":0,"pipeline":"Passed","approvals":"1/2"}
```

### MR, Russian

```json
{"kind":"mr","template":"standard","locale":"ru","title":"api!248 · Deduplicate notifications","url":"https://gitlab.example/team/api/-/merge_requests/248","summary":"Проверяет ключ события перед отправкой. На ревью: одновременные повторные запросы.","status":"Готов к ревью","author":"Alice","assignee":"Bob","milestone":"v1.2","labels":["backend"],"omitted_labels":0,"pipeline":"Успешно","approvals":"1/2"}
```

## Custom examples

Both kinds support the same custom field contract; project instructions can
provide a reusable JSON skeleton without changing the runner.

### Custom Issue, English

```json
{"kind":"issue","template":"custom","locale":"en","title":"api#123 · Duplicate notifications","url":"https://gitlab.example/team/api/-/issues/123","summary":"Agree how long event keys should be retained.","fields":[{"title":"Decision needed","value":"Retention period","short":false},{"title":"Author","value":"Alice","short":true},{"title":"Milestone","value":"v1.2","short":true}]}
```

### Custom MR, Russian

```json
{"kind":"mr","template":"custom","locale":"ru","title":"api!248 · Deduplicate notifications","url":"https://gitlab.example/team/api/-/merge_requests/248","summary":"Нужна проверка поведения при одновременных повторах.","fields":[{"title":"Ветки","value":"fix/retry → main","short":false},{"title":"Пайплайн","value":"Успешно","short":true},{"title":"Апрувы","value":"1/2","short":true}]}
```

## Design references

The layout adapts GitLab's existing
[Issue fields](https://github.com/gitlabhq/gitlabhq/blob/master/lib/gitlab/slash_commands/presenters/issue_base.rb),
[Issue presentation](https://github.com/gitlabhq/gitlabhq/blob/master/lib/gitlab/slash_commands/presenters/issue_show.rb),
and [compact search results](https://github.com/gitlabhq/gitlabhq/blob/master/lib/gitlab/slash_commands/presenters/issue_search.rb).
It is an independent stdlib implementation, not a dependency on those Ruby
presenters, an installed GitLab plugin, or its server-version requirements.
