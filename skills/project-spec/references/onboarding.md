# Existing-project onboarding

Before questions, investigate available repository evidence: instructions, README and documentation, ADR/RFC, source code, tests, schemas, configuration, CLI/API, dependencies, CI, deployment, and integrations. Use additional research only when needed; retain results in context, not the repository.

## Evidence classification

- Classify every individual claim, not a source file, subsystem, or whole project. The same evidence can confirm an implementation fact but not human intent or a compatibility guarantee.
- `KNOWN`: a concrete claim is unambiguously confirmed. Do not ask the user.
- `AMBIGUOUS`: evidence permits several interpretations. Show the options and ask the user.
- `UNKNOWN`: the repository cannot establish intent. Ask the user.
- `CONFLICT`: sources disagree. Show exact paths and differences, then ask what is normative.

For example, tests and source can make the claim "the CLI accepts `--timeout`" `KNOWN`, while "`--timeout` is a supported public contract" remains `UNKNOWN` unless confirmed by contract evidence or a person.

Do not reconstruct historical features, milestones, phases, or the original roadmap. Describe the current design and agreements the user selects as normative. Always distinguish "the code currently does this" from "this is a supported contract".

Onboarding produces only complete canonical `specs/` and ADRs when genuinely needed. Do not create `research/`, `analysis/`, `planning/`, `mapping/`, `state/`, or a research report.
