# Вклад в Agent Skills

[English](CONTRIBUTING.md) | [Русский](CONTRIBUTING.ru.md)

## Область изменений

Каждый каталог в `skills/` является authored definition, а не installation
artifact. Build должен превратить каждую definition в переносимый и
самодостаточный skill без зависимости от checkout, пользовательского home,
конкретного provider, credentials или конфигурации отдельной команды.
OpenCode-specific agents, commands и plugins находятся только в `packages/opencode/`.

Согласуйте существенное изменение поведения, совместимости или security boundary
до реализации. Новому runner-у нужен наблюдаемый контракт: JSON в stdout,
диагностика в stderr, определённые exit codes, `--help`, `--capabilities` и
подтверждённая двухфазная запись, если он меняет файлы.

## Локальная проверка

Установите закреплённые runtimes и standalone tools из корня репозитория:

```shell
mise install
task --list
```

`taskfile.yml` является единственным task graph. Локальная разработка, Lefthook
и GitHub Actions вызывают его публичные задачи, а не дублируют команды tools.
Перед отправкой любого изменения выполните единый quality gate:

```shell
task check
```

Публичный Task API разделяет проверки следующим образом:

| Задача                       | Назначение                                                    |
| ---------------------------- | ------------------------------------------------------------- |
| `tools`                      | Показать активные закреплённые инструменты.                   |
| `format`, `format:check`     | Изменить canonical formatting или проверить его без записи.   |
| `lint`, `typecheck`, `test`  | Запустить языковые проверки и тесты.                          |
| `generate`, `generate:check` | Собрать ignored artifacts или проверить их воспроизводимость. |
| `skills:validate`            | Запустить agnix, pinned skills-ref и internal contracts.      |
| `package:check`              | Выполнить полный lifecycle OpenCode package.                  |
| `eval:check`                 | Проверить schemas/corpus и hostless offline eval suite.       |
| `dependency:audit`           | Проверить locked Python и npm dependencies.                   |
| `security`                   | Проверить историю Git через gitleaks.                         |
| `check`                      | Запустить полный локальный и CI quality gate.                 |
| `pre-commit`, `pre-push`     | Выполнить наборы, которые вызывают Git hooks.                 |

`format` может изменить tracked checkout, а `task generate` записывает только
ignored artifacts. Portable authored entrypoints называются `SKILL.source.md`;
`scripts/build_skills.py` создаёт `SKILL.md` и добавляет файлы из
`shared/manifest.json` только в `.build/skills`. Команды OpenCode и copied LSP
catalog создаются только в `packages/opencode/dist/assets/` перед pack; их
источники - `packages/opencode/src/registry.ts` и `shared/references/`.

`package:check` сам выполняет `npm ci`, Prettier, oxlint, tsc, Node tests,
generated-assets drift, smoke через закреплённый OpenCode и npm pack allowlist.
Запускать отдельные npm-команды для обычной проверки не требуется.

## Git hooks

Установите hooks после bootstrap:

```shell
lefthook install
```

`pre-commit` вызывает `task pre-commit`: он выбирает быстрые non-mutating проверки
по staged paths - docs/data, Python/skills и package затрагиваются только при
изменении соответствующей области, учитывая deletions, schemas, specs и toolchain
metadata, а docs-only правка не запускает package lifecycle. `pre-push` вызывает
полный `task check`, затем `task dependency:audit`. Полный gate выполняет package
lifecycle один раз (без отдельного дублирующего package typecheck/test/generate до
`package:check`). Hooks не применяют fixes и не выполняют `git add`.

## Диагностика

- Если executable не найден, выполните `mise install` и проверьте версии через
  `mise current`.
- Если `uv run --locked` сообщает drift, не обновляйте зависимости неявно.
  Осознанно измените pin в `pyproject.toml`, затем выполните `uv lock`.
- Если `generate:check` сообщает drift, исправьте canonical source и выполните
  `task generate`. Не редактируйте build artifact напрямую.
- Agnix errors блокируют проверку. Существующие warnings печатаются полностью и
  хранятся в точном `.agnix-warnings.json`; новый warning также блокирует gate,
  пока его причина не устранена или baseline не изменён осознанно.
- Для воспроизведения package failure запустите `task package:check` из корня,
  чтобы сохранить те же версии и порядок шагов, что в CI.

## Качество и review

- Сохраняйте frontmatter и ограничения формата agentskills.io для каждого
  `SKILL.source.md`; built name - `SKILL.md`.
- Добавляйте тест для публичного контракта или существенного риска регрессии, а
  не для деталей реализации.
- Не включайте в изменения credentials, tokens, внутренние endpoints, локальные
  paths, cache или build artifacts.
- Live eval запускайте только явно с точными `--host`, `--model`, timeout,
  token/cost limits и output path. Не добавляйте model defaults или live output
  в Git; обычный CI выполняет исключительно offline suite.
- Описывайте в pull request цель, security impact, выполненные проверки и
  осознанно не запущенные проверки.
- Используйте английский для кода, комментариев и commit messages; пользовательские
  документы следуют языку существующего раздела.

## Выпуски

Версии portable skills фиксируются в их metadata. Pages distribution, версия
`@kisev/skills-opencode`, tag и GitHub Release должны относиться к одному commit.
Не изменяйте опубликованную версию: исправление выпускается новой patch-версией.
Push tag запускает единый release workflow `.github/workflows/publish.yml`. Он
сначала выполняет полный quality gate, собирает один exact npm tarball и manifest
digest-ов обоих каналов, затем публикует и проверяет Pages и npm и только после
этого создаёт GitHub Release. npm publishing использует trusted publishing через
OIDC и проверяет registry tarball, imports, CLI, signatures и provenance.
