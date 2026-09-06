# Интеграция OpenCode

`@kisev/skills-opencode` - npm package с capability router, OpenCode runtime,
управлением agent profiles и opt-in installer для agents, commands и plugins. Он
не включает portable skills и не меняет конфигурацию при import, plugin load или
npm lifecycle. Package требует Node.js 22+ и OpenCode 1.18.29+.

## Установка skills

Сначала установите нужные portable skills через `npx skills` из публичного
репозитория:

```shell
npx --yes skills add kisev/skills --agent opencode --skill '*' --copy --yes
```

Для одного skill укажите `--skill <name>`. Для воспроизводимой установки можно
передать URL GitHub tag, например
`https://github.com/kisev/skills/tree/v1.1.1`. Package никогда не устанавливает
и не обновляет skills. Если команда не нашла skill, она сообщает точную команду
`npx skills add` для его установки.

## Установка integration

Установите npm package там, где OpenCode сможет разрешить plugin:

```shell
npm install @kisev/skills-opencode@1.1.1
```

Сначала покажите план installer. По умолчанию CLI выводит короткую сводку:
счётчики по группам, только изменяемые paths, conflicts, restart flag, digest и
готовую confirm-команду. Эта команда не меняет deployment:

```shell
npm exec -- skills-opencode install --scope global --dry-run
```

Проверьте сводку и примените только показанный digest:

```shell
npm exec -- skills-opencode install --scope global --confirm <digest>
```

`global` устанавливает assets в `~/.config/opencode/agents`,
`~/.config/opencode/commands` и `~/.config/opencode/plugins`. Для текущего
repository используйте `project`:

```shell
npm exec -- skills-opencode install --scope project --dry-run
npm exec -- skills-opencode install --scope project --confirm <digest>
```

Project assets находятся в `.opencode/agents`, `.opencode/commands` и
`.opencode/plugins` текущего working directory. Scope обязателен. Installer не изменяет `opencode.json`, не
перезаписывает неизвестные или изменённые files и сохраняет ownership manifests
только после confirmed apply.

Для automation добавьте `--json`. Этот режим сохраняет полный стабильный
machine-readable plan, включая `operations` и `requires_restart`:

```shell
npm exec -- skills-opencode install --scope global --dry-run --json
npm exec -- skills-opencode agent list --scope global --json
```

Добавьте plugin в `opencode.json` вручную:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@kisev/skills-opencode"]
}
```

Полностью перезапустите OpenCode после install, upgrade или uninstall: registry
agents и commands строится до plugin hooks.

## Управление agents

Рекомендуемый интерфейс - прямой terminal CLI: он не вызывает LLM и не расходует
токены. Fixed roles `manager`, `architect`, `mapper`, `worker`, `review` и
стандартный `critic` всегда сохраняют имена и canonical prompts/permissions.
Меняются только `model` и `variant`:

```shell
npm exec -- skills-opencode agent list --scope global
npm exec -- skills-opencode agent configure manager --scope global --dry-run
npm exec -- skills-opencode agent model-set worker --scope global \
  --model openai/gpt-5 --variant high --dry-run
npm exec -- skills-opencode agent reconcile --scope global --dry-run
```

`agent configure` предлагает terminal selection в порядке provider, model,
variant по cached output `opencode models`; refresh не выполняется. Если catalog
недоступен, передайте exact `--provider <provider> --model <model>` или
`--model <provider/model>`.

Additional critic имеет имя `critic-<safe-suffix>`. Стандартный `critic` и fixed
roles нельзя удалить или переименовать:

```shell
npm exec -- skills-opencode critic add security --scope global \
  --model anthropic/claude-sonnet-4-6 --dry-run
npm exec -- skills-opencode critic remove security --scope global --dry-run
```

Для любой mutation используйте готовую confirm-команду из preview либо замените
`--dry-run` на `--confirm <digest>` и повторите те же аргументы. Человекочитаемый
plan не печатает полный JSON и сворачивает длинные группы paths. Digest связан с
одноразовым private receipt, действует 10 минут и повторно не применяется. Для
machine-readable result добавьте `--json`; поле `requires_restart` сообщает о
необходимости полностью перезапустить OpenCode.

В global scope profile configuration хранится в
`~/.config/opencode/.skills-opencode/agent-profiles.json`, а semantic deployment
manifest - рядом в `agent-profiles.manifest.json`. Для project scope те же файлы
находятся под `.opencode/.skills-opencode/`. Configuration хранит выбранные
model/variant и additional critics; package update её не сбрасывает. Manifest
хранит package version, exact critic pool и hashes canonical configuration и
rendered files.

Inventory различает `package-owned`, `managed`, `user-owned`, `drift` и exact-name
`collision`. User-owned и неизвестные agents не изменяются. Collision блокирует
apply; drift исправляется только явным `agent reconcile`. Все mutations проходят
под lifecycle lock, повторно проверяют inventory, используют journaled
all-or-rollback transaction и выполняют final validation. После прерывания
следующая mutation безопасно восстанавливает before-images и требует свежий plan.

## Upgrade и uninstall

После обновления npm package снова выполните dry-run и подтвердите новый digest.
Installer обновляет только files с совпадающим managed SHA-256.

При первом upgrade с `1.0.0` installer передаёт ownership шести fixed agents из
generic manifest в profile domain только при точном совпадении package/version,
manifest records и SHA-256 каждого файла. Любое отличие остаётся конфликтом.
Commands и plugins продолжают принадлежать generic installer. Uninstall удаляет
неизменённые deployments, но сохраняет profile configuration для последующей
установки.

```shell
npm exec -- skills-opencode uninstall --scope global --dry-run
npm exec -- skills-opencode uninstall --scope global --confirm <digest>
```

Uninstall удаляет только files из ownership manifest, если их SHA-256 не
изменился. Изменённые пользователем files остаются как `conflict`.

## Runtime options

Package экспортирует independent plugin factories `background-attempts`,
`goal-loop`, `schedule`, `autonomy-policy`, `rules-injector`, `rtk`, `zed-bell`
и `zed-clickable-paths`. Stateful plugins Background Attempts, Goal Loop,
Scheduler и Autonomy Policy отключены по умолчанию. Zed integrations также
optional. Включайте subsystem только в собственном user-owned plugin wrapper:

```js
import goalLoop from "@kisev/skills-opencode/plugins/goal-loop";

export default (input) => goalLoop(input, { enabled: true });
```

`rules-injector` fail-soft применяет ограниченный budget и пропускает native
project/global rules. `rtk` fail-open сжимает большой bash output и добавляет
подсказку для edit error, но не содержит ownership guard.

## Границы

Portable skills в корне `skills/` универсальны и устанавливаются только через
`npx skills`. Этот package поставляет только OpenCode-specific assets и runtime
router. Команды - тонкие adapters: передают `$ARGUMENTS` как недоверенный ввод
в native Skill tool, а target validation, confirmation, batch/review rules и
формат результата остаются ответственностью skill или runner.
`capabilities`, `route` и `doctor` - package tools/commands для catalog, routing и
health. Tool `agent_profiles` и четыре slash-команды `agent-list`,
`agent-model-set`, `critic-add`, `critic-remove` - optional thin UX над теми же
plan/apply contracts. Отдельного skill `agent-profiles` нет.

Package распространяется по лицензии MIT. Полные инструкции по portable skills,
upgrade и security boundaries находятся в корневом README репозитория.
