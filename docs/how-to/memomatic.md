---
audience: user
review: {"components": ["memomatic"], "sources": ["apps/memomatic/src/*", "apps/memomatic/test/*", "apps/memomatic/assets/systemd/*", "packages/agentomatic/src/installer.ts", "packages/agentomatic/test/stage19.test.mjs"], "contracts": ["specs/capabilities/applications/memomatic.md"]}
---

# Set Up and Use Memomatic

[Русский](../ru/how-to/memomatic.md)

## Install and Connect

Use Node.js 22+ and npm. For a CLI available outside an npm project:

```shell
npm install --global @kisev/memomatic
memomatic --version
```

For a project-local installation use `npm install @kisev/memomatic` and invoke
the CLI as `npx memomatic`. The systemd example below expects a global binary.

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
packages: `@kisev/agentomatic`, `@kisev/memomatic`, and `@kisev/safe-fs`.
`@latest` is the stable release channel; before a package's first stable release,
its initial registry tag can still point to a prerelease. Use explicit `@dev`
for development installations:

```shell
npm install --global @kisev/memomatic@dev
npx --yes @kisev/agentomatic@dev install --global
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

Memory files, the inbox, embeddings, rules, and Dream scheduling are preserved.
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

## Configure Dream

Before enabling session extraction, install OpenCode, configure its provider,
and choose an available model with `opencode models`. Create
`${XDG_CONFIG_HOME:-$HOME/.config}/memomatic/settings.json` with the chosen
`provider/model` identifier:

```json
{"dream": {"model": "provider/model"}}
```

```shell
memomatic dream --dry-run
memomatic dream
```

The preview leaves memory files, the persistent index, and the ingestion watermark
unchanged; configured model and embedding calls can still run. Without a model,
`dream` processes the inbox but does not extract sessions or advance their watermark.
Use `process` for a model-free inbox pass. Invalid consolidation responses fall
back to bounded append-only promotion, preserving existing curated entries.

Dream reads OpenCode sessions, including text stored in its separate `part` table.
MCP connections in other hosts share explicit memory entries but do not import
those hosts' session histories. Model calls use OpenCode's positional prompt and
JSON event output. Before enabling the timer, check `sessionsIngested` against the
available unprocessed sessions; a zero-session pass does not test model access.

## Configure Local Embeddings

Embeddings are optional and disabled by default. Without them, memory uses FTS5
text search. To add vector search with Ollama, start Ollama and install an embedding
model such as `qwen3-embedding:4b`, then merge this block into `settings.json`
alongside `dream`:

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

## Storage, Cleanup, and Recovery

The corpus is under `${XDG_STATE_HOME:-$HOME/.local/state}/memomatic/`:
`MEMORY.md`, `USER.md`, daily files in `memory/`, `DREAMS.md`, `inbox/`,
`history/`, and `archive/`. Rules belong in
`${XDG_CONFIG_HOME:-$HOME/.config}/memomatic/MEMORY_RULES.md`.

```markdown
- never-save: credentials
- auto-clean: older-than=90d scope=episodic source=stopit
```

Cleanup archives only matching unpinned old entries, preserving other entries in
the same daily file. Rejected inbox files remain in `inbox/rejected/`. Review
those files after a rejection. To recover an unwanted change, inspect the
content-addressed pre-image in `history/` or the selected entries in `archive/`,
restore the intended corpus content, then run `memomatic index`. Keep all of this
private and outside Git.

## Schedule a Sweep

The units belong to `@kisev/memomatic`, not agentomatic. Locate them with
`npm root --global`, then copy the two units from
`<npm-root>/@kisev/memomatic/assets/systemd/` to `~/.config/systemd/user/`.
Ensure the user service can resolve both `memomatic` and `opencode`; use absolute
executable paths or an explicit service PATH when a shell version manager supplies them.

```shell
systemctl --user daemon-reload
systemctl --user enable --now memomatic-dream.timer
systemctl --user status memomatic-dream.timer
journalctl --user -u memomatic-dream.service
```

Enable the timer only after the manual sweep succeeds. Stop scheduling with
`systemctl --user disable --now memomatic-dream.timer`; this preserves memory.
