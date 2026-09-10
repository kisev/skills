# Проверка

[English version](../verification.md)

## Выпуск 2.0.2

Точный portable source:
`https://github.com/kisev/skills/tree/v2.0.2`; optional package:
`@kisev/skills-opencode@2.0.2`. Portable installation закрепляет
`npx --yes skills@1.5.23`. Package требует Node.js 22+ и объявляет OpenCode
`>=1.18.29 <1.19.0`.

## Установка portable skills

Global contract для обоих поддерживаемых host:

```shell
npx --yes skills@1.5.23 add https://github.com/kisev/skills/tree/v2.0.2 --agent opencode --agent codex --skill '*' --copy --global --yes
```

Команда создаёт одну canonical copy в `~/.agents/skills`. Без `--global` project
copy находится в `.agents/skills`. `kisev/skills` выбирает latest source отдельно
от exact tag URL.

Tag-based installation при `update` остаётся pinned. Для перехода на другой tag
нужно повторить `add` с новым exact URL. Update не удаляет renamed или deleted
skills. Cleanup ограничен восемью portable names из текущего
[инвентаря миграции](migration-inventory.md); portable cleanup record `multi-run`
отсутствует.

## Интеграция OpenCode

Portable skills не зависят от npm package, а npm package не устанавливает
portable skills. Project integration постоянно хранится в project `node_modules`,
global integration - в npm project `~/.config/opencode`.

Installer требует explicit scope и preview/confirmation. Он записывает только
выбранные managed assets после confirmation и никогда не создаёт и не меняет
`opencode.json`; core entry `plugin` остаётся user-owned. Update состоит из exact
npm install, install preview, exact confirmation и перезапуска OpenCode.

Порядок uninstall: preview и confirmation удаления assets, удаление user-owned
plugin entry, npm uninstall в owning project, затем restart. Reconcile и
uninstall архивируют exact-owned assets. Conflicts, worktrees и runtime state
сохраняются; archive commands restore или purge отсутствуют.

## Текущая поверхность

Текущий inventory охватывает 29 portable skills, 33 command adapters, 6 fixed
agents, 3 selectable plugin wrappers, 5 package tools и core plugin. У package
tool `route` нет slash command.

Описания catalog проверяются по текущим skill contracts: `goal` возвращает
read-only structured Markdown не длиннее 4000 символов; `lsp-report` работает
host-neutral; task workflows storage-neutral; `code-explain` принимает current
WIP, exact range, branch или exact HTTPS MR link и показывает history без review
verdict.

## Детерминированное покрытие

Обычный quality gate не вызывает model, provider или credential:

```shell
task eval:check
task check
```

Committed corpus содержит English trigger, English near-miss, Russian trigger и
Russian near-miss для каждого active skill. Deterministic checks покрывают
registration, configuration, installer ownership, archive/reconcile behavior,
agent discovery, negative inputs, path escapes, malformed results, incomplete
budgets и secret leakage.

Compatibility checks проверяют OpenCode `1.18.29` и `1.18.30` внутри
`>=1.18.29 <1.19.0` без credentials.

## Live evaluation и clean checkout

Live evaluation не входит в `task check`. Для него явно нужны trusted-live mode,
host, model, timeout, token и cost budgets и output path. Default model или
baseline нет, untrusted CI не получает credentials.

Generated runtime copies и distribution outputs проверяются на parity. В clean
temporary checkout build и check должны оставить `git status` неизменным:
declared generated copies tracked, temporary outputs остаются ignored.
