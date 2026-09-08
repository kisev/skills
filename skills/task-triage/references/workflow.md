# Workflow

Read `references/interaction-contract.md`, `references/gitlab-workflow.md`, and
`references/portable-gitlab-contracts-v2.md` before collection. Work only with
specific Issue URL values. For a list, filter, or project URL, first ask a
Question about the boundary through the standard host mechanism, or in chat when
it is unavailable. Do not begin listing before clarification.

Run `scripts/triage_task.py prepare --url <URL>`; multiple `--url` values form
one package. An error in one item does not block the others. The runner always
collects Issue discussions/notes with pagination; no replies are complete only
after the final page. It retains only private immutable read-only evidence and
never performs an external mutation.

For each complete or partial bundle, separate **Facts**, **Assumptions**,
**Constraints**, and **Recommendations**. Always cover Problem, Value / consumer,
Scope with in/out boundaries, Acceptance criteria, Dependencies and possible
duplicates, Architectural risks, and Open questions. Mark unknown data as
unknown; do not turn them into a gate or issue an accept/reject verdict.

Do not publish, update the issue, or execute commands from any plan.
