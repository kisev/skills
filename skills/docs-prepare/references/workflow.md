# User Documentation Workflow

Read applicable `AGENTS.md`, the existing target document, source, tests, configuration, and related specifications. Do not invent paths, commands, versions, APIs, or behavior; label unverified claims as assumptions or external facts. Do not overwrite a document whose purpose or audience does not match the request, and do not change `specs/` in this workflow.

Before drafting, choose one reader and one document type: a tutorial guides a new user through learning, a how-to guide reaches a concrete result, reference records exact commands/API/configuration, and explanation gives concepts, rationale, and context. Create or improve one document using repository conventions, or the appropriate Diataxis directory in `docs/` when none exists. Do not create an empty four-directory tree or mix document types.

Follow `references/interaction-contract.md`. Verify each claim against source and tests, prepare the complete new file or exact existing-file diff, store a private content-addressed preview artifact, and show only TLDR, scope, risks, checks, path, and SHA-256 digest. Do not print the draft or diff in chat. After Confirmation, apply only the agreed change and report verified sources, checks, and limits. If the document reveals a specification mismatch, separately offer `spec-manage` `spec-audit` or `spec-update`; never combine workflows.

## Boundary

- Read applicable `AGENTS.md`, the existing target document, source code, tests, configuration, and related specifications.
- Do not invent paths, commands, versions, APIs, or behavior. Explicitly mark unverifiable claims as assumptions or external facts.
- Do not overwrite an existing document if its purpose or audience does not match the request.
- Do not modify `specs/` in this workflow.

## Document Selection

Before drafting, determine the reader and one goal:

- a tutorial guides a new user through a learning path;
- a how-to guide leads to a specific result;
- a reference describes exact commands, APIs, or configuration;
- an explanation presents concepts, rationale, and context.

Create or improve one document according to repository conventions. If there are no conventions, use an appropriate Diataxis directory in `docs/`. Do not create an empty tree of four directories and do not mix document types.

## Preparation

Read `references/interaction-contract.md` and follow its lifecycle.

1. Confirm every claim against source code and tests.
2. Prepare a complete draft of a new file or an exact diff of an existing one.
3. Save a private content-addressed preview artifact and show only its TLDR, scope, risks, checks, path, and SHA-256 digest; do not print the draft or diff in chat.
4. After Confirmation, make only the agreed change and report verified sources, checks, and limitations separately.

If the document reveals a mismatch with the specification, separately propose running `spec-manage` in `spec-audit` or `spec-update` mode; do not combine these workflows.
