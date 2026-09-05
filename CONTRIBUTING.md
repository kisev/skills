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

| Задача                       | Назначение                                                  |
| ---------------------------- | ----------------------------------------------------------- |
| `tools`                      | Показать активные закреплённые инструменты.                 |
| `format`, `format:check`     | Изменить canonical formatting или проверить его без записи. |
| `lint`, `typecheck`, `test`  | Запустить языковые проверки и тесты.                        |
| `generate`, `generate:check` | Создать materialized assets или проверить drift без записи. |
| `skills:validate`            | Запустить agnix, pinned skills-ref и internal contracts.    |
| `package:check`              | Выполнить полный lifecycle OpenCode package.                |
| `security`                   | Проверить историю Git через gitleaks.                       |
| `check`                      | Запустить полный локальный и CI quality gate.               |
| `pre-commit`, `pre-push`     | Выполнить наборы, которые вызывают Git hooks.               |

Только `format` и `generate` меняют tracked checkout. Если меняются shared
references, сначала измените canonical-файл в `shared/references/`, затем
запустите `task generate` и включите materialized copies в то же изменение.
Команды из `packages/opencode/assets/commands/` также генерируются: их источником
служит `packages/opencode/src/registry.ts`.

`package:check` сам выполняет `npm ci`, Prettier, oxlint, tsc, Node tests,
generated-assets drift, smoke через закреплённый OpenCode и npm pack allowlist.
Запускать отдельные npm-команды для обычной проверки не требуется.

## Git hooks

Установите hooks после bootstrap:

```shell
lefthook install
```

`pre-commit` вызывает быстрый non-mutating `task pre-commit`. `pre-push` вызывает
полный `task check`. Hooks не применяют fixes и не выполняют `git add`.

## Диагностика

- Если executable не найден, выполните `mise install` и проверьте версии через
  `mise current`.
- Если `uv run --locked` сообщает drift, не обновляйте зависимости неявно.
  Осознанно измените pin в `pyproject.toml`, затем выполните `uv lock`.
- Если `generate:check` сообщает drift, исправьте canonical source и выполните
  `task generate`. Не форматируйте generated/materialized copy напрямую.
- Agnix errors блокируют проверку. Существующие warnings печатаются полностью и
  хранятся в точном `.agnix-warnings.json`; новый warning также блокирует gate,
  пока его причина не устранена или baseline не изменён осознанно.
- Для воспроизведения package failure запустите `task package:check` из корня,
  чтобы сохранить те же версии и порядок шагов, что в CI.

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
`@kisev/skills-opencode`, tag и GitHub Release должны относиться к одному commit.
Не изменяйте опубликованную версию: исправление выпускается новой patch-версией.
Публикация npm package запускается только push tag из
`.github/workflows/publish.yml`: workflow сверяет tag с версией package и
использует npm trusted publishing через OIDC. v1.0.0 - одноразовый
интерактивный bootstrap до создания package relationship.
