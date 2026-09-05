# Интеграция OpenCode

`@kisev/skills-opencode` - npm package с capability router, OpenCode runtime и
opt-in installer для agents, commands и plugins. Он не включает portable skills и
не меняет user config при import, plugin load или npm lifecycle. Package требует
Node.js 22+ и OpenCode 1.18.29+.

## Установка skills

Сначала установите нужные portable skills через `npx skills` из публичного
репозитория:

```shell
npx --yes skills add kisev/skills --agent opencode --skill '*' --copy --yes
```

Для одного skill укажите `--skill <name>`. Для воспроизводимой установки можно
передать URL GitHub tag, например
`https://github.com/kisev/skills/tree/v1.0.0`. Package никогда не устанавливает
и не обновляет skills. Если команда не нашла skill, она сообщает точную команду
`npx skills add` для его установки.

## Установка integration

Установите npm package там, где OpenCode сможет разрешить plugin:

```shell
npm install @kisev/skills-opencode@1.0.0
```

Сначала покажите план installer. Эта команда не создаёт files:

```shell
npm exec -- skills-opencode install --scope global --dry-run
```

Проверьте exact operations и примените только показанный digest:

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
перезаписывает неизвестные или изменённые files и сохраняет ownership manifest
только после confirmed apply.

Добавьте plugin в `opencode.json` вручную:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@kisev/skills-opencode"]
}
```

Полностью перезапустите OpenCode после install, upgrade или uninstall: registry
agents и commands строится до plugin hooks.

## Upgrade и uninstall

После обновления npm package снова выполните dry-run и подтвердите новый digest.
Installer обновляет только files с совпадающим managed SHA-256.

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
`capabilities`, `route` и `doctor` - package tools/commands только для catalog,
routing и health; они не устанавливают и не исправляют package или skills.

Package распространяется по лицензии MIT. Полные инструкции по portable skills,
upgrade и security boundaries находятся в корневом README репозитория.
