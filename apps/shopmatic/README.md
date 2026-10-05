# shopmatic

[Русская версия](README.ru.md)

MCP stdio server for shopping research on marketplace storefronts through the
`agent-browser` CLI. It answers three tools — `shopmatic_search`,
`shopmatic_product`, and `shopmatic_compare` — with one unified JSON schema
(name, price, URL, rating) and runs every anonymous query in a fresh,
proven-empty browser profile.

## Why a browser

Marketplace consumer APIs are closed, and ready third-party MCP scrapers are
out of scope by decision. shopmatic therefore drives a real browser through
`agent-browser` (pinned in the root `mise.toml`), extracts the rendered SPA
results, and returns structured data. Direct HTTP endpoints are deliberately
not used.

## Marketplace status

| Marketplace | Status | Evidence |
| - | - | - |
| Wildberries | supported | spike extraction of search results, 2026-10-05 |
| Yandex Market | supported | spike extraction of search results, 2026-10-05 |
| Ozon | blocked | antibot challenge never resolves from a datacenter network; the spike stop condition forbids bypass work |

A blocked marketplace stays registered and answers an explicit error instead
of pretending support.

## Anonymous mode and account mode

Anonymous mode is the default and is mandatory for every automated call: each
run creates a fresh profile directory under
`$XDG_CONFIG_HOME/shopmatic/profiles/anonymous/` (mode 0700), proves the
profile has no cookies before the first navigation, and deletes it after the
browser closes. Host marketplace sessions are never reused.

Account mode is opt-in and manual only. Run `shopmatic login <marketplace>`,
log in by hand in the opened browser window, and the persistent private
profile keeps the session for later `--account` runs. shopmatic never enters
credentials itself and never performs account actions.

## Install and run

The package is built and run from this repository with uv; `agent-browser`
must be on `PATH` (the pinned Mise tool provides it):

```shell
uv run --locked shopmatic --version
uv run --locked shopmatic serve            # MCP stdio server
uv run --locked shopmatic search wildberries "клавиатура" --max-price 5000
uv run --locked shopmatic compare "клавиатура" --limit 5
uv run --locked shopmatic product wildberries 12345678
uv run --locked shopmatic login yandex-market
```

Connect the MCP server from a host with:

```json
{"mcpServers": {"shopmatic": {"command": "uv", "args": [
  "--directory", "/path/to/apps/shopmatic", "run", "--locked", "shopmatic", "serve"]}}}
```

Tool calls return unified JSON; blocked marketplaces and rendering failures
return explicit tool errors. `SHOPMATIC_AGENT_BROWSER` overrides the browser
executable and `SHOPMATIC_PROFILE_ROOT` overrides the profile root (used by
the test suite).

## Unified result schema

```json
{
  "schema": "kisev-skills/shopmatic-result/v1",
  "marketplace": "wildberries",
  "kind": "search",
  "query": "клавиатура",
  "items": [
    {"position": 1, "id": "1474531458", "name": "…", "price": 119.0,
     "old_price": 255.0, "currency": "RUB", "rating": 4.8, "rating_votes": 8721,
     "url": "https://www.wildberries.ru/catalog/1474531458/detail.aspx"}
  ],
  "warnings": []
}
```

Ratings are absent where the storefront did not render them (Wildberries
renders ratings lazily); such rows carry explicit `null`s and the envelope may
carry a warning. Compare answers wrap per-marketplace envelopes under
`comparisons`.

## Safety boundaries

Read-only interactions with the storefronts: search, product cards, no cart,
orders, or checkout. Credentials and cookies live only in the XDG private
profile, never in Git, logs, or tool answers. Extraction selectors break when
a marketplace redesigns its pages; that transport risk is accepted by
decision, and a failing adapter answers an explicit error instead of guessing.

## Development

```shell
uv run --locked pytest
uv run --locked mypy
uv run --locked ruff check .
```

The application-local `pyproject.toml` mirrors the repository lint selection.
Tests run fully offline against a scripted fake `agent-browser` executable;
no test talks to a marketplace.
