# Архитектура

## Источник истины

Единственный canonical checkout сопровождающего находится в
`/home/kisev/Projects/Github/kisev/skills`. Другие локальные копии не являются
источником изменений или установки.

Переносимые skills находятся в `skills/<name>/` и являются законченными
единицами установки. Во время работы skill может использовать только файлы под
собственным корнем. `shared/` - входные данные сопровождающего, а не runtime-
зависимость установленного skill. `scripts/build_skills.py` создаёт точные копии
по manifest только в ignored `.build/skills`; source tree не содержит copies.

Для `askme`, `task-prepare`, `task-review` и read-only `goal` canonical
`shared/references/work-item-contract.schema.json`, описание контракта и
stdlib-only `work_item.py` materialize-ятся в каждый skill. Установленный skill
использует только свою копию. Validator отдельно возвращает machine findings и
structured semantic assessment, затем детерминированно вычисляет verdict
`ready`, `needs_clarification` или `blocked`.

В корне репозитория нет пользовательского CLI. Отдельный npm package предоставляет
CLI `skills-opencode` только для OpenCode integration. Maintainer scripts могут
использовать только Python stdlib; Python runners, если они нужны skill, находятся
внутри этого skill.

`packages/skills/package.json` описывает непубликуемый build-only package
`@kisev/skills`. `scripts/build_distribution.py` собирает `.build/packages/skills`:
well-known index, lock с SHA-256 каждого archive, source revision и один archive
на skill с root `SKILL.md`. Это boundary будущего unpkg distribution; в source
tree не появляются archive, runtime copies, generated commands или copied LSP
catalog.

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

## Инварианты build

- JSON manifest - единственное отображение общих исходников в пути build skills,
  включая minimal Python runtime для автономных runner-ов.
- Пути относительные, нормализованные и ограничены соответственно каталогами
  `shared/references/` и isolated build output.
- Symlinks в исходных и конечных путях отклоняются.
- Source tree не меняется; build output заменяется только после полной подготовки.
- `--check` сравнивает существующий artifact с clean staging и сообщает о drift.
- Проверка work item сортирует findings по стабильному ключу и связывает report с
  digest item/evidence, поэтому неизменный повторный check даёт тот же verdict.
- LSP applicability использует один machine-readable catalog, добавляемый в built
  `lsp-report` вместе со stdlib-only runtime и в package staging. Portable report
  не имеет npm runtime dependency; package doctor дополняет только host
  config/status facts.
