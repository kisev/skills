# Docs Site

[English](README.md)

Astro-сайт документации коллекции портативных Agent Skills. Публикуется на
GitHub Pages по адресу `https://kisev.github.io/skills` рядом с
установочными эндпоинтами дистрибутива: HTML-сайт живёт в корне, а
`index.json`, `skills-lock.json`, `.well-known/`, `archives/` и `dev/`
остаются нетронутыми каналами установщика.

Проект намеренно не является членом корневых workspaces: это приватное
приложение только для сборки (в npm ничего не публикуется), поэтому он хранит
собственный `package-lock.json` и не участвует в графе публикации npm,
которым управляет `docs/how-to/npm-package-lifecycle.md`.

## Команды

Сайт собирается через собственный lockfile из корня репозитория:

```shell
mise exec -- npm ci --prefix apps/docs-site
mise exec -- npm run build --prefix apps/docs-site
mise exec -- npm test --prefix apps/docs-site
```

Задачи `task site:build` и `task site:test` оборачивают те же команды;
`site:build` входит в `task check:core` и обе задачи композиции Pages, а
`dependency:audit` проверяет lockfile сайта.

## Модель контента

- `scripts/sync-content.mjs` читает frontmatter из
  `skills/*/SKILL.source.md` и `shared/skill-relations.json`, валидирует их и
  генерирует `src/generated/skills.ts` (вне Git). Расхождение ломает сборку.
- `src/content/examples/{en,ru}/<skill>.md` — по одному разобранному примеру
  взаимодействия на документ: запрос, действия скилла и полученный артефакт.
  Zod-схема в `src/content.config.ts` отвергает битые и неполные примеры, а
  `tests/test_site_contract.py` требует паритета EN/RU.
- Маршруты существуют для обеих локалей: английский в корне (`/skills/...`),
  русский под `/ru/...` (`/ru/skills/...`).
- Pagefind индексирует собранный сайт после `astro build`; страницы каталога
  подключают стандартный поисковый UI из `/skills/pagefind/`.

## Композиция Pages

`scripts/compose_pages_site.py` принимает `--site-dir apps/docs-site/dist` и
копирует сборку в staging-корень Pages до каналов дистрибутива: файлы
дистрибутива всегда выигрывают коллизию, а `.nojekyll` гарантирует, что
Jekyll не выбросит ассеты Astro с подчёркиванием в начале имени.
