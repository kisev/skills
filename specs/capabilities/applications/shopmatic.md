---
review: {"components": ["shopmatic"], "sources": ["apps/shopmatic/src/*", "apps/shopmatic/tests/*"], "contracts": ["specs/architecture/09-architecture-decisions/0020-drive-marketplace-storefronts-through-agent-browser.md"]}
---

# Application `shopmatic`

## Purpose

Provide shopping research on consumer marketplace storefronts through an MCP
stdio server that drives a real browser via the `agent-browser` CLI. The
server exposes search, product card, and comparison tools, answers every call
with one unified JSON schema, and runs all automated queries anonymously in a
fresh, proven-empty browser profile.

## Triggers and Near-Misses

Used when the user asks to find, price, or compare products across supported
marketplaces; near-miss: cart, order, or checkout actions, which shopmatic
never performs.

## Inputs/Outputs

Input is an MCP tool call (`marketplace`, `query`, optional price cap and
limit) or an equivalent CLI invocation; output is one unified JSON envelope
per marketplace: `schema`, `marketplace`, `kind`, `query`, `items`
(position, id, name, price, old_price, currency, rating, rating_votes, URL),
and optional warnings. The Python application resolves the pinned
`agent-browser` through `PATH` (or `SHOPMATIC_AGENT_BROWSER`) and keeps
profiles under `$XDG_CONFIG_HOME/shopmatic` (or `SHOPMATIC_PROFILE_ROOT`).

## Workflow Stages

Resolve the marketplace registry → start a browser session bound to a
profile → for anonymous runs, prove the fresh profile is cookie-empty before
the first navigation → open the search URL with the price bound → probe the
rendered DOM until results appear, an antibot challenge is detected, or the
bounded probe budget expires → trigger lazy rendering where the storefront
needs it → evaluate the marketplace extraction script → parse the payload
into the unified schema → close the browser and discard the anonymous
profile. Comparison wraps one search per selected marketplace under one
`comparisons` answer.

### REQ-F-564 - Run anonymous-first with proven-empty profiles

Automated calls shall run in anonymous mode by default: each call launches a
fresh profile directory, verifies the profile contains no cookies before the
first navigation, never reuses a host marketplace session, and deletes the
profile after the browser closes. Profile storage shall live outside the
repository under the shopmatic XDG root, shall use 0700 directories and 0600
files, and shall reject symlinks and foreign owners on every boundary check.
Account mode shall exist only as an explicit local command that opens a
headed browser for the user to log in by hand; the persistent account profile
is private, marketplace-scoped, and never filled by the application.

#### Verification

Offline tests cover private-directory creation and mode checks, symlink and
file rejection, relative `XDG_CONFIG_HOME` rejection, persistent
account-profile identity, profile wipe and discard, an anonymity violation
failing the run before navigation, and anonymous profiles being absent after
a completed run while account profiles persist.

### REQ-F-565 - Keep marketplace support spike-gated and errors explicit

Only marketplaces that passed the recorded `agent-browser` spike shall answer
search, product, or compare calls; every other registered marketplace shall
answer an explicit blocker error naming the spike evidence. Antibot
challenges, render timeouts, and unparseable extraction payloads shall surface
as explicit errors or warnings in the unified envelope; the application shall
not fall back to direct HTTP endpoints, shall not retry past its bounded
budgets, and shall not guess data it did not extract. Ratings that the
storefront did not render are explicit nulls, optionally accompanied by an
envelope warning.

#### Verification

Offline tests cover a blocked marketplace answering a spike-naming error
before any browser launch, antibot and never-render probe outcomes failing
with distinct explicit errors, unparseable extraction payloads failing,
missing name or URL rows being dropped, non-finite and out-of-range prices
and ratings being coerced to null, and limits bounding result rows.

## Dependencies

Python 3.12+ standard library only at runtime; `agent-browser` (pinned in the
root `mise.toml`) with its Chrome for Testing browser as the execution
transport; uv with an application-local lock, and ruff plus strict mypy as
application-local dev tools. The application is not published to npm and is
not part of the portable skill distribution.

## Remote/Local Effects

Read-only requests to supported storefronts: search URLs and product pages,
no cart, order, or checkout actions. Local effects are limited to the XDG
profile tree; anonymous profiles are discarded after each call, so no
marketplace cookie survives a run. Account profiles persist only because the
user logged in deliberately.

## Errors/Partial/Escalation

A blocked marketplace answers its blocker without launching a browser. A
challenge page, a render timeout, a failed browser command, a timeout, or an
unparseable payload each produce one explicit error; warnings inside a
successful envelope mark partially rendered data (for example, missing lazy
ratings). Invalid input fails before any browser interaction.

## Requirement

### REQ-I-427 - Expose shopping research through explicit MCP tools

The application shall expose exactly `shopmatic_search`, `shopmatic_product`,
and `shopmatic_compare` through an MCP stdio server speaking newline-framed
JSON-RPC 2.0, with tool input schemas covering marketplace, query, price cap,
and limit arguments. Tool answers shall carry the unified schema JSON as text
content; blocked marketplaces and rendering failures shall be tool-level
errors with their reason. The same operations shall be available as CLI
subcommands (`search`, `product`, `compare`, `login`, `serve`) so a user can
run the runbook without an MCP host.

#### Verification

Offline tests cover the JSON-RPC handshake, notification silence, the tool
list and input schemas, search/product/compare answers over a scripted fake
browser, blocked-marketplace and unknown-tool error envelopes, protocol
error codes for unknown methods and malformed requests, and the CLI exit-code
mapping including the invalid-input boundary.
