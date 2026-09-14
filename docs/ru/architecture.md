# Архитектура

[English](../architecture.md) | [Русский](architecture.md)

## Источник истины

Portable definitions находятся в `skills/<name>/` с authored entrypoints
`SKILL.source.md` и уникальными resources. `shared/` - единственный source общих
контрактов и runtime, а не зависимость установленного skill. Декларативный
`shared/manifest.json` отображает exact shared files в build paths.
`scripts/build_skills.py` создаёт полные skills только в `.build/skills` и не
записывает generated copies в authored tree.

Для `askme`, `task-prepare`, `task-review` и read-only `goal` canonical
`shared/references/work-item-contract.schema.json`, описание контракта и
stdlib-only `work_item.py` добавляются в каждый built skill. Установленный skill
использует только свою копию. Validator отдельно возвращает machine findings и
structured semantic assessment, затем детерминированно вычисляет verdict
`ready`, `needs_clarification` или `blocked`.

В корне репозитория нет пользовательского CLI. Отдельный npm package предоставляет
CLI `skills-opencode` только для OpenCode integration. Maintainer scripts могут
использовать только Python stdlib; Python runners, если они нужны skill, находятся
внутри этого skill.

`packages/skills/package.json` является private version manifest portable
distribution. `scripts/build_distribution.py` собирает GitHub Pages payload в
`.build/packages/skills`: standard well-known index, release metadata и по одному
content-addressed SHA-256 archive с root `SKILL.md` на skill. Push tag развёртывает
этот payload по адресу `https://kisev.github.io/skills`.

## Интеграция с host

Переносимые skills описывают задачу и не требуют конкретного host. Host может
предоставить штатный инструмент интерактивных вопросов; если его нет, agent
задаёт вопрос в чате. OpenCode-only adapters, agents, commands, plugins и
capability router относятся к необязательному package `packages/opencode/` и не
нужны для установки или работы portable skill. Package не содержит копий skills.
OpenCode commands, LSP catalog и authored agent/plugin assets materialize-ятся в
`packages/opencode/dist/assets/` перед `npm pack`. Его явный installer применяет
эти build assets после dry-run и matching digest;
upgrade/uninstall сохраняют user drift через ownership manifests. Canonical agent
assets содержат prompts/permissions, отдельная profile configuration -
models/variants и additional critics, а semantic manifest - rendered hashes и
package version. Stateful plugins являются opt-in и при отключении не создают
state, timers, sessions или mutations.

## OpenCode runtime

Шесть specialized skills с Python runner устанавливаются как обычные self-contained Agent Skills; `goal` является read-only prompt-only adapter.
Их Python runner materialize-ит общий stdlib runtime внутрь skill и использует
только XDG/OpenCode user-owned config/state. Package runtime не ссылается на
checkout и экспортирует семь независимых plugin factories. `capabilities`,
`route` и `doctor` являются package tools для catalog/routing/health. Doctor
использует общий versioned read-only facts API direct CLI и package tool: он не
вызывает plugin factories, lifecycle recovery, receipts, journals или LSP
servers. Host-only resolved config и `lsp.status` при наличии SDK добавляются как
allowlisted facts, иначе получают `unavailable/incomplete`. `/doctor` остаётся
thin adapter, отдельного portable skill `doctor` нет. Routing
receipt одноразово связывает выбранного agent с canonical task text, exact
requirements, execution-card digest/revision, matrix revision и TTL; переходы
отклоняют stale, replay, изменённый task/card и просроченный receipt.
`agent_profiles` - optional adapter над package-domain planner; основной интерфейс
управления agents - прямой CLI без LLM. Все mutations используют private receipt,
lifecycle lock, final revalidation и journaled rollback/recovery.
Stateful runtime records используют те же private 0600 atomic writes и lock;
при повторной загрузке незавершённые background attempts переходят в
`orphaned`, а недопустимые status transitions отклоняются.

### Routing и контракты этапа 18

`doit` - единственный владелец lifecycle evidence -> plan -> confirmation ->
execution -> checks -> report. OpenCode `manager` только адаптирует его к Task и
не создаёт второй lifecycle. Package route имеет четыре назначения:
exploration -> `mapper`, architecture -> `architect`, implementation -> `worker`,
review -> `review` или один выбранный `critic`; documentation и quick остаются у
`doit`.

Inventory routing разрешается только из host config. Caller не может передать
agents, capabilities, tools, models или availability. Versioned receipt одноразово
и с TTL связывает task, requirements, destination, agent, execution card и
revision host inventory. Versioned cards и mapper/worker/review/critic reports
проверяются на реальных Task dispatch/result hooks. Card фиксирует write и
forbidden paths, steps, checks, явные VCS operations и отдельные confirmations
для execution, publication и history rewrite.

## Инварианты build

- JSON manifest отображает canonical shared inputs только в build paths, включая
  minimal Python runtime для автономных runner-ов.
- Authored skill trees содержат `SKILL.source.md` и не содержат generated
  destinations.
- `--check` проверяет source parity и artifacts без изменения authored files.
- Supported installer читает well-known Pages index и проверяет digest каждого
  archive перед installation.
- Пути относительные, нормализованные и ограничены соответственно каталогами
  `shared/references/` и isolated build output.
- Symlinks в исходных и конечных путях отклоняются.
- Source tree не меняется; build output заменяется только после полной подготовки.
- `--check` сравнивает существующий artifact с clean staging и сообщает о drift.
- Release checks связывают Pages version и source revision с exact tag.
- Проверка work item сортирует findings по стабильному ключу и связывает report с
  digest item/evidence, поэтому неизменный повторный check даёт тот же verdict.
- LSP applicability использует один machine-readable catalog, добавляемый в built
  `lsp-report` вместе со stdlib-only runtime и в package staging. Portable report
  не имеет npm runtime dependency; package doctor дополняет только host
  config/status facts.
