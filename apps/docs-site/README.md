# Docs Site

[Русский](README.ru.md)

The Astro documentation site for the portable Agent Skills collection. It
publishes to the GitHub Pages project URL `https://kisev.github.io/skills`
alongside the installer distribution endpoints: the HTML site lives at the
root, while `index.json`, `skills-lock.json`, `.well-known/`, `archives/`, and
`dev/` stay untouched installer channels.

This project is intentionally not a root workspace member. It is a private
build-only application (nothing is published to npm), so it keeps its own
`package-lock.json` and stays out of the npm publication graph that
`docs/how-to/npm-package-lifecycle.md` governs.

## Commands

Run the site through its own lockfile from the repository root:

```shell
mise exec -- npm ci --prefix apps/docs-site
mise exec -- npm run build --prefix apps/docs-site
mise exec -- npm test --prefix apps/docs-site
```

`task site:build` and `task site:test` wrap the same commands; `site:build`
runs inside `task check:core` and both Pages composition tasks, and
`dependency:audit` covers the site lockfile.

## Content model

- `scripts/sync-content.mjs` reads `skills/*/SKILL.source.md` frontmatter and
  `shared/skill-relations.json`, validates them, and generates
  `src/generated/skills.ts` (Git-ignored). A mismatch fails the build.
- `src/content/examples/{en,ru}/<skill>.md` holds one worked interaction
  example per document: the request, what the skill does, and the produced
  artifact. The zod schema in `src/content.config.ts` rejects broken or
  partial examples, and `tests/test_site_contract.py` enforces EN/RU parity.
- Routes exist for both locales: English at the root (`/skills/...`) and
  Russian under `/ru/...` (`/ru/skills/...`).
- Pagefind indexes the built site after `astro build`; the catalog pages load
  the default search UI from `/skills/pagefind/`.

## Pages composition

`scripts/compose_pages_site.py` accepts `--site-dir apps/docs-site/dist` and
copies the build into the staged Pages root before the distribution channels,
guaranteeing distribution files win any collision and `.nojekyll` is present
for Astro's underscore-prefixed asset directories.
