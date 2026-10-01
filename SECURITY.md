# Security Policy

[Русский](SECURITY.ru.md)

## Reporting a Vulnerability

Do not post a potential vulnerability, credentials, or proof of concept in
Issues, Discussions, or a pull request. Open a private security advisory from
the repository's Security tab and include the affected version, reproduction
conditions, expected and actual behavior, and possible impact. If GitHub does
not offer private reporting, do not disclose details publicly. First request a
private channel from a maintainer through the repository owner's profile.

Do not include real tokens, passwords, MFA codes, personal data, or production
system data. Use revoked or synthetic values.

## Project Boundaries

- Portable skill assets must not depend on files outside their installed skill
  root.
- Python runners use only the standard library and install no dependencies.
- External, user-configuration, destructive, history, release, and package lifecycle flows require a preview and confirmation; the OpenCode installer
  requires interactive consent or an explicit `--yes`; config apply binds its
  in-process preview to source bytes and a one-use expiring receipt.
- Code review preparation never publishes: it produces a private `runbook.md`
  with direct copy-ready `glab` commands and an interactive plan viewer. The user
  runs each command and checks GitLab afterwards; no reservations, receipts,
  locks, or expiry block a repeated send. GitLab remains the remote authority.
- A confirmed install with core selected merges the plugin into `opencode.json`
  and may provision npm dependencies. It has no npm lifecycle hooks and preserves
  unrelated user entries and modified assets.
- Only the `rtk` wrapper is preselected by default. External authentication
  remains in user-owned configuration and must never pass through a prompt,
  `argv`, or logs.

## Supported Versions

The latest published stable releases of the portable skills and npm package are
supported. The stable GitHub Pages index advances only on a new release tag and
binds each content-addressed archive to a SHA-256 digest; a mismatch aborts
without installation. Security fixes are published as a new patch release;
existing tags and published archive contents are not rewritten.
