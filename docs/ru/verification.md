# Проверка

[English version](../verification.md)

## Дополнительное резюме выпуска 2.0.0

Annotated tag `v2.0.0`, npm package `@kisev/skills-opencode@2.0.0` и GitHub
Release должны ссылаться на один exact commit. Portable skills устанавливаются
напрямую из immutable Git tag через `npx --yes skills@1.5.23`; для exact migration
с `v1.2.0` используйте URL tag и `--agent opencode` или `--agent codex`.

Migration inventory фиксирует переименования и удаления skills, command/plugin
поверхностей и пустой набор aliases. `reconcile` сохраняет retired exact-owned
assets в private content-addressed archive со статусом `archive-pending`; purge
не выполняется, а изменённые и user-owned файлы остаются conflicts. Package tool
`route` сохранён, но slash-команда `/route` и старые action/mode aliases не входят
в выпуск.

Optional OpenCode package совместим с `>=1.18.29 <1.19.0`, проверяется на
`1.18.29` и `1.18.30` и требует Node.js 22+. Portable skills от него не зависят.
Ограничения выпуска: Mattermost ещё не имеет полной parity, runtime state и
`doctor` требуют hardening, stateful plugins остаются opt-in, а live eval не
входит в обычный quality gate.

Этап 20 проверяет публичный контракт `2.0.0` без модели, сети, провайдера и
учётных данных. `task eval:check` валидирует зафиксированный corpus и запускает
все детерминированные assertions; эта задача входит в `task check`.

Для каждого из 29 skills есть четыре сценария: English trigger, English
near-miss, Russian trigger и Russian near-miss. Пары trigger/near-miss сохраняют
одинаковые structured outcome и mutation boundary. ID и digest сценариев стабильны,
а ошибочные дубликаты prompts блокируются тестами corpus.

Детерминированные контракты покрывают 29 skills, 33 command adapters, 6 agents, 3
выбираемых plugins, 5 package tools и core infrastructure plugin. Зафиксированный
negative corpus проверяет duplicate identity, digest drift, пропущенные RU/EN пары,
неизвестные surfaces, выход из пути, malformed results, неполные budgets, утечку
секретов, неподдерживаемый host и устаревший package inventory.

В `evals/contracts/opencode-compatibility.json` зафиксированы минимум OpenCode
`1.18.29` и актуальный релиз `1.18.30` внутри `>=1.18.29 <1.19.0`. Build,
registration, config, installer и agent discovery проверяются для обоих слотов без
учётных данных.

Live eval не входит в `task check`. Для него явно обязательны `--trusted-live`, host,
model, timeout, token/cost budgets и output path. Default model/baseline отсутствуют,
а untrusted CI не получает secrets и не запускает live gate.

Generated copies и build outputs проверяются на parity. В чистом временном checkout
build/check и полный `task check` не должны менять `git status`; committed copies
отслеживаются, временные outputs игнорируются.
