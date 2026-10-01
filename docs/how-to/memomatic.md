---
audience: user
review: {"components": ["memomatic"], "sources": ["apps/memomatic/src/*", "apps/memomatic/test/*", "apps/memomatic/assets/systemd/*", "packages/agentomatic/src/installer.ts", "packages/agentomatic/test/stage19.test.mjs"], "contracts": ["specs/capabilities/applications/memomatic.md"]}
---

# Set Up and Use Memomatic

[Русский](../ru/how-to/memomatic.md)

## Install and Connect

Use Node.js 22.13+ and npm. For a CLI available outside an npm project:

```shell
# Registry version
npm view --prefer-online @kisev/memomatic@latest version

# Install
npm install --global @kisev/memomatic

# Installed package and active CLI
npm list --global @kisev/memomatic --depth=0
memomatic --version
```

Tags can move between preview and installation. `npm list` checks the package;
`--version` checks the CLI resolved from PATH. For a project-local installation:

```shell
# Registry version
npm view --prefer-online @kisev/memomatic@latest version

# Install in this npm project
npm install @kisev/memomatic

# Installed dependency and local CLI (no npx download)
npm list @kisev/memomatic --depth=0
./node_modules/.bin/memomatic --version
```

Invoke the project CLI as `npx memomatic`. The systemd example below expects a
global binary. npx itself does not install a global CLI.

Connect `memomatic mcp-serve` as a local stdio MCP server in each host. OpenCode,
Kilo, and MiMo use this fragment in their respective JSON configuration:

```json
{
  "mcp": {
    "memomatic": {
      "type": "local",
      "command": ["memomatic", "mcp-serve"],
      "enabled": true
    }
  }
}
```

Merge it with existing MCP entries. If a service cannot resolve a shell-managed
binary, use absolute executable paths. Restart the host and check that
`memory_write`, `memory_search`, `memory_get`, and `memory_forget` appear under the
MCP server (the host may prefix tool names). Models decide when to search; ask
explicitly when recall is required. There is no automatic memory injection.

Memomatic and agentomatic are separate installations; agentomatic does not install
or depend on memomatic.
`@dev` selects the latest successful publication from `dev` for all workspace
packages: `@kisev/agentomatic`, `@kisev/memomatic`, `@kisev/taskmatic`, and `@kisev/safe-fs`.
`@latest` is the stable release channel; before a package's first stable release,
its initial registry tag can still point to a prerelease. Use explicit `@dev`
for development installations:

```shell
# Registry versions
npm view --prefer-online @kisev/memomatic@dev version
npm view --prefer-online @kisev/agentomatic@dev version

# Install and confirm the OpenCode setup
npm install --global @kisev/memomatic@dev
npx --yes @kisev/agentomatic@dev install --global

# Installed packages and active memory CLI
npm list --global @kisev/memomatic --depth=0
npm list --prefix "$HOME/.config/opencode" @kisev/agentomatic --depth=0
memomatic --version
```

Updating agentomatic alone does not update the memomatic CLI or MCP server.

## Migrate from the OpenCode Plugin

Rerun the [agentomatic installer](opencode-integration.md) with your existing
selections except `memomatic`, which is no longer a plugin option. Review the
preview: unchanged manifest-owned `plugins/memomatic.js` is archived and removed.
An edited wrapper is a conflict; preserve your edits and resolve it before retrying.
If you manually configured an import of `@kisev/agentomatic/plugins/memomatic`,
remove that entry yourself. Then connect the MCP server as above and restart
OpenCode. Installing only the newer npm dependency does not remove an old wrapper.

Memory files, the inbox, embeddings, rules, and existing sweep scheduling are
preserved.
The former `projects` settings map is ignored; project and trigger annotations
remain stored on existing entries but no longer drive automatic recall.

## Save and Retrieve a First Entry

Ask the agent to call `memory_write` with `text: "Use a separate preview before publishing."`
and `source: "user"`. The result identifies a queued inbox file, not an indexed fact.
Then run:

```shell
memomatic process
memomatic search "preview publishing"
```

Use `memory_get` with the returned file and line to retrieve the complete entry.
Search results identify source and personal/team visibility. A personal entry must
not be copied into shared artifacts. `memory_forget` removes one explicitly selected
line; ordinary model consolidation cannot authorize deletion of curated memory.

## Configure Sessions and Dream

Sessions and Dream are separate sweeps. `memomatic sessions` extracts episodic
memory from OpenCode session transcripts; `memomatic dream` consolidates:
inbox, promotion of usage-gated episodic entries into `MEMORY.md`, a bounded
rewrite, and archiving. Dream never reads OpenCode history itself.

Before enabling session extraction, install OpenCode, configure its provider,
and choose an available model with `opencode models`. Create
`${XDG_CONFIG_HOME:-$HOME/.config}/memomatic/settings.json` with the chosen
`provider/model` identifier:

```json
{"sessions": {"model": "provider/model"}}
```

A legacy `{"dream": {"model": "provider/model"}}` value is still adopted for
sessions until the `sessions` section overrides it.

```shell
memomatic sessions --dry-run
memomatic sessions
memomatic dream
```

The previews leave memory files, the persistent index, and the ingestion watermark
unchanged; configured model and embedding calls can still run. Without a model,
`sessions` is skipped without advancing the watermark; `dream` still processes
the inbox and archives by rules, but performs no consolidation model calls. Use
`process` for a model-free inbox pass. Invalid consolidation responses fall
back to bounded append-only promotion, preserving existing curated entries.

The sessions command reads OpenCode sessions from its V2 database, ingesting
only user and assistant text. A pre-V2 database is not parsed; start OpenCode V2
once so it migrates the history, then rerun the sweep. MCP connections in other
hosts share explicit memory entries but do not import those hosts' session
histories. Model calls reuse one isolated OpenCode V2 server per run, with tools
denied, or an explicitly configured existing server. Before enabling the timer,
check `sessionsIngested` against the available unprocessed sessions; a
zero-session pass does not test model access.

## Observe, Limit and Resume Dream

```shell
memomatic sessions --plan --json
memomatic sessions --max-duration 15m --timeout 3m --log-format json
memomatic sessions --max-sessions 2 --progress never
memomatic dream --plan --json
memomatic status
memomatic sessions --help
```

`sessions --plan` only reads the session snapshot and checkpoints: no model
calls, embeddings, or persistent writes. `dream --plan` counts pending inbox
files and promotion candidates the same way. `status` reports the queue
without a model: pending inbox files, the session backlog (or `null` when no
OpenCode database exists), promotion candidates, and the last dream/sessions
run. Unlike `--plan`, `--dry-run` can still incur model and embedding usage.
Normal Sessions drains all eligible work captured at startup; messages
arriving later belong to the next run. There is no default 20-session cap.
The first upgrade from the legacy creation-time watermark checks existing
history once, because that watermark cannot identify processed message
revisions. Current memory is retained. Inspect `--plan` and use limits to
spread a large migration over multiple invocations. This is re-ingestion, not
deletion or replacement of the existing memory corpus.

| CLI option | Environment | `sessions` setting / default |
| - | - | - |
| `--model` | `MEMOMATIC_MODEL` | `model`: configured provider/model |
| `--variant` | `MEMOMATIC_VARIANT` | `variant`: provider default |
| `--timeout` | `MEMOMATIC_TIMEOUT` | `timeoutMs`: 180000 |
| `--max-duration` | `MEMOMATIC_MAX_DURATION` | `maxDurationMs`: 0 (unlimited) |
| `--max-sessions` | `MEMOMATIC_MAX_SESSIONS` | `maxSessions`: 0 (all) |
| `--chunk-chars` | `MEMOMATIC_CHUNK_CHARS` | `maxChars`: 24000 |
| `--retries` | `MEMOMATIC_RETRIES` | `retries`: 1 additional attempt |
| `--idle` | `MEMOMATIC_IDLE` | `idleMs`: 600000 |
| `--opencode-url` | `MEMOMATIC_OPENCODE_URL` | `opencodeUrl`: private server per run |
| `--database` | `MEMOMATIC_DATABASE` | OpenCode XDG database |

Dream keeps `--model`, `--variant`, `--timeout`, `--max-duration` and
`--retries` for its consolidation model; the matching settings live in the
`dream` section (`model` also serves as the sessions fallback). Legacy
extraction knobs previously read from `dream` migrate to `sessions`
automatically on first load.

Duration flags accept `ms`, `s`, `m`, or `h`; a bare number means milliseconds.
Settings-file durations are numeric milliseconds. Common logging, JSON and color
controls follow the [CLI reference](../reference/cli.md).

Local SQL filters text parts before loading them. Unchanged modern session
revisions skip body parsing; changed messages are fingerprinted and split without
truncating the final outcome. Only adjacent exact duplicate messages are dropped;
there is no heuristic "important message" filter. Each fragment includes a bounded
overlap of preceding context. Model interpretation can still miss a distant
reference; it is instructed not to invent unresolved meaning.

Completed extraction responses are stored privately under `history/ingestion/`
with source session/message identifiers, not full transcripts. Each fragment is
applied idempotently before its checkpoint is advanced. Ctrl-C, a timeout or a
later failure retains earlier completed work. Run the same command to continue;
do not remove the run lock while its owner is alive. The lock no longer expires
merely because a run exceeds 30 minutes. After interruption the index may lag
committed Markdown; resume the interrupted command or run `memomatic index` to
refresh it.

Stages, counts, elapsed time, retries and wait heartbeats go to stderr. The final
JSON report includes model call counts, sent characters and actual token/cache
usage when OpenCode supplies it; absent usage is explicitly marked unavailable,
not estimated as exact. A session limit reports unscanned sessions separately
from the remaining fragments in the selected batch.

The default executor reuses provider configuration and authentication through
OpenCode, disables external plugins/skills for its own server, and denies tools
in its extraction sessions. Its loopback server uses an ephemeral password and
is stopped on completion or cancellation. `--opencode-url` instead uses a server
you own, with `OPENCODE_SERVER_USERNAME`/`OPENCODE_SERVER_PASSWORD` when required;
it never stops that server. Credentials are not CLI arguments or log fields.

`memomatic index` now reuses vectors when model identity and text are unchanged.
Use `memomatic index --force` to deliberately regenerate all vectors or repair
an index after a model alias changes weights/dimensions. `memomatic status`
only inspects state and no longer rebuilds the index.

## Configure Local Embeddings

Embeddings are optional and disabled by default. Without them, memory uses FTS5
text search. To add vector search with Ollama, start Ollama and install an embedding
model such as `qwen3-embedding:4b`, then merge this block into `settings.json`
alongside `sessions` and `dream`:

```json
{
  "embedding": {
    "url": "http://127.0.0.1:11434/v1/embeddings",
    "model": "qwen3-embedding:4b"
  }
}
```

The URL must be an OpenAI-compatible embeddings endpoint, not Ollama's
`/api/embed`. Memomatic sends entry and query text to this endpoint; a loopback
endpoint keeps embedding requests local. No dimension setting is needed.
Run `memomatic index` after changing the model, then check `memomatic search`.
Keep the endpoint available for indexing and search: an embedding request failure
is reported as an error rather than silently falling back to text-only search.

## Search Quality and Diagnostics

```shell
memomatic index
memomatic search "routing decisions" --explain
memomatic search "deployment" --project atlas --explain
```

After upgrading from an index without model metadata, run `memomatic index` once.
This rebuilds derived search data and embeddings, not your Markdown knowledge or
session history. Changing the embedding endpoint/model requires another reindex;
same-sized vectors from different models are not compatible. A failed embedding
rebuild preserves the previous committed index and reports an error.

For Qwen3-Embedding, search automatically adds the model's `Instruct`/`Query`
retrieval instruction to queries; documents remain raw. Other models use raw
queries unless `embedding.queryInstruction` is configured. An explicit empty
instruction disables query wrapping. Query-only instruction changes do not require
rewriting document vectors.

Full token matches rank first. Lexical coverage and vector similarity are checked
before importance and age adjustments; lexical evidence never lowers relevance.
Semantic-only hits must reach `search.minSemanticScore` (default `0.45`). The
general `search.minScore` remains `0.35`; thresholds are configurable and are not
probabilities. These defaults were checked with a small local Qwen3 positive/negative
sample, not a universal benchmark. The same query can behave differently with a
different model. A high threshold may miss a weak but useful paraphrase.

`--explain` shows matched tokens, lexical coverage, cosine similarity, relevance,
age and importance factors, and the acceptance reason. MCP accepts `explain: true`
and `project` on `memory_search`. No accepted hits prints `No relevant memory found.`
in the CLI and returns `[]` through MCP. An embedding error is not reported as an
empty successful search.

A project filter includes exactly that project's entries plus user-level memory;
old entries without project annotations are not assigned a scope automatically.
Keep human-authored instructions in repository/host instruction files. Retrieved
experiences and preferences are evidence, not authority to override those rules.
This follows the [Z.ai memory principles](https://docs.z.ai/devpack/resources/memory-mechanism):
separate instructions from learned memory, scope retrieval, and keep updates
inspectable. Explicit MCP retrieval remains the only agent interface.

## Storage, Cleanup, and Recovery

The corpus is under `${XDG_STATE_HOME:-$HOME/.local/state}/memomatic/`:
`MEMORY.md`, `USER.md`, daily files in `memory/`, `DREAMS.md`, `inbox/`,
`history/`, and `archive/`. Rules belong in
`${XDG_CONFIG_HOME:-$HOME/.config}/memomatic/MEMORY_RULES.md`.

```markdown
- never-save: credentials
- auto-clean: older-than=90d scope=episodic source=stopit
- auto-clean: older-than=180d scope=episodic unused-after=30d
```

Cleanup archives only matching unpinned old entries, preserving other entries in
the same daily file. The optional `unused-after=Nd` suffix adds usage-aware
decay: episodic entries older than `Nd` days that never earned a useful recall
are archived earlier, while recalled entries live up to the full `older-than`
window or promotion. Decay is inactive unless the suffix is present. Rejected
inbox files remain in `inbox/rejected/`. Review
those files after a rejection. To recover an unwanted change, inspect the
content-addressed pre-image in `history/` or the selected entries in `archive/`,
restore the intended corpus content, then run `memomatic index`. Keep all of this
private and outside Git.

## Schedule the Sweeps

The units belong to `@kisev/memomatic`, not agentomatic. Locate them with
`npm root --global`, then copy the four units from
`<npm-root>/@kisev/memomatic/assets/systemd/` to `~/.config/systemd/user/`.
Ensure the user service can resolve both `memomatic` and `opencode`; use absolute
executable paths or an explicit service PATH when a shell version manager supplies them.

```shell
systemctl --user daemon-reload
systemctl --user enable --now memomatic-sessions.timer memomatic-dream.timer
systemctl --user status memomatic-sessions.timer memomatic-dream.timer
journalctl --user -u memomatic-sessions.service
journalctl --user -u memomatic-dream.service
```

Sessions run early (02:00 with jitter) and Dream later (04:30 with jitter), so
extraction normally finishes before consolidation starts. Both sweeps share one
run lock: if an unusually long sessions run ever overlaps Dream, that Dream
invocation fails fast with `another memomatic run is active` and the next
scheduled run takes over. Enable the timers only after the manual sweeps
succeed. Stop scheduling with
`systemctl --user disable --now memomatic-sessions.timer memomatic-dream.timer`;
this preserves memory.
