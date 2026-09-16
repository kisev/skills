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
- Write-capable flows require a preview and confirmation; the OpenCode installer
  accepts only the digest of a previously shown plan.
- The code-review publication helper accepts one previously shown action digest,
  revalidates live GitLab state, and never supports batch or force. It inherits
  user-owned `glab` environment configuration at execution without serializing
  credentials or environment values into plans, argv, prompts, or logs.
- The installer does not modify `opencode.json`, has no npm lifecycle hooks, and
  does not overwrite unmanaged or user-modified files.
- Optional plugin wrappers are unselected by default. External authentication
  remains in user-owned configuration and must never pass through a prompt,
  `argv`, or logs.

## Supported Versions

The latest published stable releases of the portable skills and npm package are
supported. The stable GitHub Pages index advances only on a new release tag and
binds each content-addressed archive to a SHA-256 digest; a mismatch aborts
without installation. Security fixes are published as a new patch release;
existing tags and published archive contents are not rewritten.
