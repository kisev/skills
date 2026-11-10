# Workflow Router

The mandatory start is `run-path.md`. It owns the primary path from the target
to the chat report. Every stage reads only its own file, never the whole set up
front. The correctness and style references are applied when their stage says
so.

| Stage | File |
| - | - |
| Target, release routing, environment and OCR version, startup round | `run-path.md` |
| Profiles, aliases, provider and model selection | `session-modes.md` |
| Task baseline and its confirmation | `context-package.md` |
| Collection, exact refs, completeness, redaction | `run-path.md` |
| OCR background authoring and the 8000-byte limit | `run-path.md` |
| OCR runs, parallel processes, merging | `review-panel.md` |
| Incrementality, sessions, compare and resume | `incremental-review.md` |
| Runbook sections and the chat report | `output-format.md` |
| Draft notes, the head check, replies | `publication.md` |
| Reply voice and thread replies | `discussion-replies.md` |
| Plain language | `clarity-rules.md` |
| Optional final editing pass | `humanize-patterns.md` (apply `humanize` as an optional pass; do not invoke it for every reply) |
| Finding evidence and minimum fixes | `finding-examples.md` |
| Architecture paragraph | `architecture-checklist.md` |
| SemVer impact | `semver.md` |
| User-facing prose language | `language-policy.md` |

The runtime helper commands and their printed contracts are the only format
source for their inputs and outputs. Never read the runtime's source code or
dump a schema to derive a field. A command that refuses names the exact missing
or invalid input; report it and stop rather than guessing.

The one-page map of the review line is the repository page
`docs/reference/mr-review.md`.
