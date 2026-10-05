# ADR-0020: Drive marketplace storefronts through agent-browser

- Status: accepted
- Date: 2026-10-05
- Supersedes: none

## Context

The agent had no way to search or compare products across the storefronts the
user actually buys from (Wildberries, Ozon, Yandex Market). Ready-made
third-party marketplace MCP scrapers were rejected by decision, buyer-facing
marketplace APIs are closed, and a direct HTTP transport was also rejected —
an unauthenticated HTML/API client would own the anti-bot arms race without a
browser. This is the first outbound network egress from an application under
`apps/` to third-party commercial sites, and it is not the first network
component of the repository: portable skills already call Mattermost over
HTTPS, and tooling already calls the GitLab API; neither precedent covers
scraping a hostile consumer SPA.

What was not proven was whether `agent-browser` (pinned in the root
`mise.toml`) can extract data from these storefronts stably enough to build on.
Per the agreed stop conditions, that question had to be answered by a
time-boxed throwaway spike before any server, schema, gate, or decision
landed.

## Decision

Build `apps/shopmatic` as an MCP stdio server that drives a real browser
through the `agent-browser` CLI and nothing else. The server exposes three
tools — `shopmatic_search`, `shopmatic_product`, and `shopmatic_compare` —
and answers all of them with one unified JSON result schema (name, price,
URL, rating, currency). Browser processes launch with an isolated empty
profile, a clean user agent, and no automation-control feature flags; the
anonymous profile is proven cookie-empty before the first navigation and
discarded after the run. Persistent login is opt-in, manual, and local: the
user runs a login command, signs in by hand in a headed window, and the
profile stays under `$XDG_CONFIG_HOME/shopmatic` with the mattermost private
path discipline (0700 directories, 0600 files, no symlinks, owner-checked).

Marketplace support is spike-gated. The spike passed for Wildberries and
Yandex Market; Ozon's antibot challenge never resolves from a datacenter
network, so Ozon stays registered as blocked and its tools answer an explicit
blocker error. No bypass work is built for a blocked storefront, and no HTTP
fallback exists — a render failure or challenge answers an explicit error.

## Alternatives

A ready-made third-party marketplace MCP was rejected by user decision
(trust, supply chain, and credential boundaries outside our control). A
direct HTTP hybrid was rejected by user decision before the spike. Driving
Playwright or Puppeteer in-process was rejected because `agent-browser` is
already pinned, session-isolating, and skill-compatible, and adding a second
browser stack would duplicate that. A headless-only HTTP scraper was rejected
with the direct transport. Dropping Ozon from the registry entirely was
rejected: keeping it registered with its blocker keeps the tool surface
honest and documents the stop condition instead of pretending the
marketplace does not exist.

## Migration and Tradeoffs

This is the first shopmatic release; there is no migration. The accepted
tradeoffs are transport-level: storefront redesigns break extraction
selectors (accepted by decision — the adapter answers an explicit error
instead of guessing), ratings render lazily on some storefronts (rows carry
explicit nulls plus a warning), and account-mode cookies increase the blast
radius of a storefront ban (accepted: read-only queries, user's own account).
Automation markers are removed with documented launch configuration, not
evasion tooling; a storefront that still blocks the network stays blocked.
Runtime credentials and cookies live only in the XDG profile tree, never in
Git, logs, or tool answers.

## Verification

The application requirements live in
[shopmatic](../../capabilities/applications/shopmatic.md): the MCP surface in
[REQ-I-427](../../capabilities/applications/shopmatic.md#req-i-427---expose-shopping-research-through-explicit-mcp-tools),
anonymous-first isolation in
[REQ-F-564](../../capabilities/applications/shopmatic.md#req-f-564---run-anonymous-first-with-proven-empty-profiles),
and spike-gated support in
[REQ-F-565](../../capabilities/applications/shopmatic.md#req-f-565---keep-marketplace-support-spike-gated-and-errors-explicit).
Canonical prose follows [REQ-C-001](../../requirements/constraints/README.md#req-c-001---english-only-canonical-specification)
and is owned by `spec-manage`. The application-local gate
(`task shopmatic:check`) runs the offline test suite against a scripted fake
browser, strict mypy, ruff, the uv build, and the CLI version contract; live
storefront verification is a manual runbook in `docs/verification.md`, not
part of any automated gate.
