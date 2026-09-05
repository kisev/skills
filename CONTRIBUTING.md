# Вклад в Agent Skills

## Область изменений

Каждый каталог в `skills/` должен оставаться переносимой и самодостаточной
единицей. Не добавляйте зависимости на checkout, пользовательский home, конкретный
provider, credentials или конфигурацию отдельной команды. OpenCode-specific
agents, commands и plugins находятся только в `packages/opencode/`.

Согласуйте существенное изменение поведения, совместимости или security boundary
до реализации. Новому runner-у нужен наблюдаемый контракт: JSON в stdout,
диагностика в stderr, определённые exit codes, `--help`, `--capabilities` и
подтверждённая двухфазная запись, если он меняет файлы.

## Локальная проверка

Используйте Python 3.12+ и Node.js 22+. Перед отправкой изменения выполните
проверки, относящиеся к затронутой области:

```shell
python3 scripts/sync_shared.py --check
python3 -m unittest discover -s tests -v
for skill in skills/*; do uvx --from skills-ref agentskills validate "$skill"; done
npx --yes skills add . --list
```

Для изменения `packages/opencode/` выполните также:

```shell
npm ci
npm run typecheck
npm run generate-assets
git diff --exit-code
npm test
npm pack --dry-run
```

Последние шесть команд запускаются из `packages/opencode/`. Если меняются shared
references, сначала измените канонический файл в `shared/references/`, затем
запустите `python3 scripts/sync_shared.py` и включите materialized copies в тот же
изменение. Не редактируйте такие copies вручную.

## Качество и review

- Сохраняйте frontmatter и ограничения формата agentskills.io для каждого
  `SKILL.md`.
- Добавляйте тест для публичного контракта или существенного риска регрессии, а
  не для деталей реализации.
- Не включайте в изменения credentials, tokens, внутренние endpoints, локальные
  paths, cache или build artifacts.
- Описывайте в pull request цель, security impact, выполненные проверки и
  осознанно не запущенные проверки.
- Используйте английский для кода, комментариев и commit messages; пользовательские
  документы следуют языку существующего раздела.

## Выпуски

Версии portable skills фиксируются в их metadata. Версия
`agent-skills-opencode`, tag и GitHub Release должны относиться к одному commit.
Не изменяйте опубликованную версию: исправление выпускается новой patch-версией.
