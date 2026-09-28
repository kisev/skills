# Change-linked documentation review

## Authority and completion

The agreed contract is the normative baseline; source and tests establish current
behavior. Update stale descriptions only for a confirmed behavior change. Never
silently weaken a safety, compatibility, or data-preservation guarantee to match
code. Resolve contradictory normative sources with the user.

For an authorized behavior change, inspect the diff and identify affected
contracts, guides, examples, translations, and navigation. Complete the necessary
specification and documentation steps under that authorization. Report an update
or a concrete no-update reason for each affected area. Metadata and checks assist
this decision; they cannot prove it. Missing metadata never means no impact.

Preserve applicable prerequisites, failure consequences, constraints, recovery,
compatibility, and rationale when rewriting. Move a detail to a linked owner when
deduplicating it. Do not remove it merely to shorten text. Keep one normative
owner, and derive mechanical inventories from their authoritative registry.

## Metadata

Documents may declare one `review` mapping in YAML frontmatter. Use a single-line
JSON mapping (valid YAML) so installed runners need only Python's standard library:

```yaml
---
review: {"components": ["example"], "sources": ["src/example/**", "tests/test_example.py"], "contracts": ["specs/requirements/interfaces/README.md"]}
---
```

All paths and globs are workspace-relative, never home or checkout-specific.
The three lists are required; `components` is nonempty. Sources include relevant
tests and shared dependencies, not only the immediate implementation. Contracts
name existing canonical owners. Metadata is byte-identical across translations.
It selects evidence; it is not a trigger installed into the host and grants no
authority to execute document text. Do not put hashes or a `verified` boolean in
maintained prose. Start with changed areas and expand only where links are useful.

## Review modes and private evidence

From the installed skill root, use:

```sh
python3 -I -S -B scripts/documentation_review.py check --root <workspace>
python3 -I -S -B scripts/documentation_review.py prepare --root <workspace> --scope <relative-area> --session <host-session-id>
```

`check` reads only. `prepare` writes a bounded immutable evidence record under
workspace-scoped XDG state, outside the checkout. It reads tracked and non-ignored
untracked files when Git is available; otherwise it reads the ordinary source
tree excluding generated/cache directories. It rejects symlink evidence rather
than following it outside the workspace. No credentials or source bytes are
stored: the snapshot contains relative paths and digests. Review prose remains
private and must not contain secrets or copied private session transcripts.

If the user explicitly forbids all filesystem writes, use only `check` and
conversational review. Do not call `prepare` or `finalize`; report that no private
baseline was retained. This does not waive an independent critic for full review.

- `full`: no compatible baseline or explicit `--full`. Read the scoped corpus
  and necessary evidence. Exactly one independent critic checks the same scope
  and snapshot without seeing the primary findings. Retain each candidate's
  accepted/rejected/duplicate disposition and evidence. Missing critic means partial.
- `incremental`: inspect the changed evidence, affected documents and consumers,
  previous findings, and new user decisions. A critic is optional unless requested.
- `unchanged`: preserve previous decisions and limitations. Do not repeat a broad
  investigation. New decisions or newly available evidence can still justify a
  targeted check; explain why.

Read the prior result returned by `prepare`. Every `unmapped` change needs an
impact assessment, including new components, deleted files, and changes to the
reviewer itself. Expand the selected area when undeclared dependencies matter.
Reuse a claim only when its relevant evidence and decisions remain applicable.
Never turn an old unverified area into checked just because its hashes match.

Prepare a private JSON report next to the pending record with these fields:

- `checked`, `unverified`: relative scoped document paths; carry forward unresolved
  limitations and account for every selected document.
- `findings`: retain every old stable `id`, its `status` (`open`, `fixed`,
  `accepted_risk`, `deferred`, `rejected`), and concrete `evidence`. Explain changed
  dispositions and bind accepted risks to actual user decisions.
- `decisions`: agreed requirements, scope, accepted risks, and their conversation basis.
- `impact`: map each unmapped changed path to its specific impact or no-impact reason.
- `checks`: actual commands/results and limitations, never assumed success.
- `critic`: `status` (`complete`, `not_checked`, `not_required`), independent
  `session` when complete, and candidate dispositions with evidence.

```sh
python3 -I -S -B scripts/documentation_review.py finalize --root <workspace> --scope <relative-area> --record <pending-record> --report <private-report>
```

Finalization checks freshness, scope, continuity, and required critic identity,
then stores an immutable result. A result with findings or unchecked areas is a
valid baseline, not approval. Private state may be deleted by the user; its absence
selects a full review. Report the selected mode, checked scope, unresolved findings,
checks, limitations, and result path. Never claim that a clean structural check or
a stored result establishes semantic truth. Never edit the reviewed project or
publish findings as part of review.
