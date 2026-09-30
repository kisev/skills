# ADR-0017: Observable incremental CLI processing

- Status: accepted
- Date: 2026-09-28
- Supersedes: none

## Context

Dream previously launched a full OpenCode run for each of at most twenty sessions,
buffered output until completion, had no model-call deadline and repeatedly
embedded unchanged memory. Creation-time cursors missed continuations of old
sessions and a prefix-only limit omitted conversation outcomes. Standalone CLI
parsers had weak contextual help; `dream --help` could execute the operation.

## Decision

Retain OpenCode provider/auth integration. Use one owned, tool-denied OpenCode
server per sweep, with an explicit existing-server option, timeouts, observable
retries and process-group cleanup. Default to draining the startup snapshot;
limits are optional overrides. Perform SQL filtering, revision checks, exact
deduplication and fragment preparation locally. Models interpret only new or
changed prepared text. Keep conservative context overlap rather than heuristic
importance filtering. Persist compact extraction receipts and idempotent
fragment checkpoints; cache document embeddings and unchanged consolidation.

Use Commander plus a common authored TypeScript runtime, materialized into the
three existing packages at build time. The user rejected a new npm package name.
This duplicates generated output, not authored logic, and keeps archives usable
without a checkout or cross-package runtime imports. Keep the agentomatic wizard
and machine contracts; add shared configuration/logging controls and contextual
help to the standalone tools.

## Alternatives

Direct provider HTTP would require independent credential/provider support and
was rejected in favor of OpenCode. Aggressive local semantic filtering could save
tokens but miss decisions and was rejected. A default capped sweep was rejected
in favor of completing the captured queue. A separate shared npm package was
rejected to avoid another publication/bootstrap lifecycle.

## Migration and Tradeoffs

The legacy cursor cannot prove which message revisions were seen. The user chose
one conservative recheck of prior history while retaining current memory.
`dream --plan` exposes its size without model calls, and optional limits spread
that work across resumable runs. Existing memory and task data are not reset.
The initial migration can be substantially more expensive than later incremental
runs. Characters are not presented as exact token counts. Bounded overlap can
leave distant references unresolved; the model must not invent their meaning.

Partial runs retain committed Markdown and may leave its derived index behind
until a successful index pass. An owned OpenCode server is stopped on exit;
existing user servers and user service/configuration files are not changed.
Model calls remain sequential by default to keep checkpoint ordering and provider
load predictable. Logs expose timing and usage before any further concurrency
optimization is considered.

## Verification

See [REQ-F-544](../../capabilities/applications/memomatic.md#req-f-544---drain-a-bounded-snapshot-with-observable-resumable-processing)
and [REQ-I-419](../../requirements/interfaces/README.md#req-i-419---share-cli-parsing-and-observability-without-another-npm-package).
