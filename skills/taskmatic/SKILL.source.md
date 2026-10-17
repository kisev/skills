---
name: taskmatic
description: >-
  Run a local-first task board for people and agents: SQLite cards with a
  markdown mirror, agent claims with heartbeats, a read-only web board, and
  an MCP server. Use when the user asks to work with the local task board:
  cards, claims, or the board itself.
  Russian discovery terms: доска задач, канбан, задачи для агентов, вести задачи,
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
---

# taskmatic

Before any other work in the first session, run `python3 scripts/check_environment.py` from the skill directory and show its output: it prints one OK/FAIL line per external tool from `references/requirements.json` (`@kisev/taskmatic`) with the copy-ready install command for every failure. It installs nothing and makes no network call; never install a tool automatically, print the command for the user.

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md`. Preserve exact commands, paths,
IDs, JSON fields, and quotations. Use the independently installed
`@kisev/taskmatic` application (Node.js 22.13+) through CLI or MCP. This skill
contains instructions and the snapshot contract, not a bundled runtime.
