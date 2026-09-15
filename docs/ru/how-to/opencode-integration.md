# Интеграция OpenCode

[English](../../how-to/opencode-integration.md)

`@kisev/skills-opencode` - optional OpenCode-specific слой. У portable
skills отдельный lifecycle: их нужно установить независимо через
[инструкцию по portable skills](portable-skills.md).

## Требования и ownership

Package требует Node.js 22+ и OpenCode `>=1.18.29 <1.19.0`.

| Component          | Project scope                | Global scope                                      |
| ------------------ | ---------------------------- | ------------------------------------------------- |
| npm package        | project `node_modules`       | `node_modules` в npm project `~/.config/opencode` |
| Commands           | `.opencode/commands`         | `~/.config/opencode/commands`                     |
| Agents             | `.opencode/agents`           | `~/.config/opencode/agents`                       |
| Optional wrappers  | `.opencode/plugins`          | `~/.config/opencode/plugins`                      |
| Ownership metadata | `.opencode/.skills-opencode` | `~/.config/opencode/.skills-opencode`             |

Package и generated wrappers должны оставаться доступными после завершения
installer. Import, plugin loading и npm lifecycle scripts не устанавливают
assets или portable skills и не меняют OpenCode configuration.

## Постоянная установка package

### Project scope

Установите package в npm project репозитория и запускайте CLI из его корня:

```shell
cd /path/to/project
npm install --save-exact @kisev/skills-opencode
npx --yes @kisev/skills-opencode@latest install --scope project --dry-run
```

Package остаётся в project `node_modules`, confirmed assets размещаются в
`.opencode`.

### Global scope

Используйте `~/.config/opencode` как постоянный npm project:

```shell
mkdir -p "$HOME/.config/opencode"
cd "$HOME/.config/opencode"
test -f package.json || npm init --yes
npm install --save-exact @kisev/skills-opencode
```

Сохраните dependency в `package.json` и lock file этого npm project. Confirmed
assets размещаются в `~/.config/opencode`. После persistent install запускайте
CLI-команды global scope из любого каталога:

```shell
npx --yes @kisev/skills-opencode@latest install --scope global --dry-run
```

## Выбор assets

В TTY команда `install` открывает четыре группы: Skill command adapters, Package
command adapters, Fixed agents и Selectable plugins. Две command-группы и шесть
fixed agents изначально выбраны, optional plugins - нет. Skill command adapters
это OpenCode slash-команды, загружающие уже установленный одноимённый portable
skill. Package command adapters вызывают package tools. Выбор adapter не выбирает
и не устанавливает skill. В каждой группе можно выбрать произвольный набор:
Up/Down перемещает курсор, Space переключает item, A выбирает всё, N снимает
выбор, Enter подтверждает, Escape отменяет.

Вне TTY передайте все три selection group. Этот пример выбирает три commands,
всех fixed agents и ни одного wrapper:

```shell
npx --yes @kisev/skills-opencode@latest install --scope project \
  --commands doctor,reconcile,agent-profiles \
  --agents manager,architect,mapper,worker,review,critic \
  --plugins none --dry-run
```

Если вне TTY передан любой selection flag, обязательны `--commands`, `--agents`
и `--plugins`. Точные текущие имена показывает команда:

```shell
npx --yes @kisev/skills-opencode@latest capabilities --json
```

Selectable wrappers: `rules-injector`, `rtk`, `zed-bell`.

## Активация core plugin

Installer записывает, нужна ли selection core integration, но никогда не создаёт
и не меняет `opencode.json`. Добавьте package в user-owned массив `plugin` для
того же scope, сохранив существующие entries:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@kisev/skills-opencode"]
}
```

Для project scope храните package в project `node_modules`, а configuration - в
project. Для global scope храните npm project и user configuration в
`~/.config/opencode`. После activation или изменения assets перезапустите
OpenCode.

## Preview и confirm

Каждая mutation начинается с `--dry-run`. Preview показывает operations,
conflicts, необходимость restart, срок действия receipt, отдельные plan и
confirmation digests и точную confirmation command. Если reconcile показывает
modified managed files или ownership conflicts, он блокируется: receipt и Apply
command не создаются. Сначала установите или обновите текущий package,
примените его exact installer confirmation, затем повторите reconcile; ownership
conflicts нужно разрешить вручную.

```shell
npx --yes @kisev/skills-opencode@latest install --scope project --dry-run
```

Обязательный OpenCode flow: persistent npm install, `install --dry-run`, exact
confirmation command из preview, добавление package в user-owned `plugin` и
перезапуск OpenCode. Persistent npm project в `~/.config/opencode` сохраняет
доступность global plugin; stable npx-команды с `--scope global` можно запускать
из любого каталога. Перед каждым reconcile установите или обновите package и
примените его installer plan.

Preview имеет deterministic `plan_digest` и unique `confirmation_digest`. Новый
dry-run в том же scope supersede-ит любой старый unconsumed preview, включая
preview другой package или agent operation; старая confirmation отклоняется.

Выполните команду из preview со всеми selection flags. Receipts приватны,
действуют 10 минут, применяются один раз и связаны с action, scope, root и
текущим inventory. Apply отклоняет stale state и unsafe conflicts.

## Doctor

`doctor` читает integration facts без создания receipts, recovery journals,
запуска plugins или LSP servers:

```shell
npx --yes @kisev/skills-opencode@latest doctor --scope project
npx --yes @kisev/skills-opencode@latest doctor --scope project --json
```

Report содержит versions, ownership, drift, collisions, archive counts, redacted
configuration projections, runtime summaries и LSP facts. Raw configuration,
environment values, receipts, credentials и secrets не сериализуются. Exit
status `0` означает чистое состояние, `1` - findings, `2` - invalid input или
incomplete probe failure.

## Обновление

В npm project, которому принадлежит dependency, установите текущий stable package
и сохраните exact resolved version, покажите и подтвердите `install` с тем же
scope и нужной selection, затем перезапустите OpenCode:

```shell
npm install --save-exact @kisev/skills-opencode
npx --yes @kisev/skills-opencode@latest install --scope project --dry-run
```

Используйте полную confirmation command из preview. Installer обновляет только
files с совпадающими recorded ownership и SHA-256. User-owned или modified
managed files остаются conflicts. Package update не сбрасывает выбранные agent
models, variants, additional critics или retained profile configuration.

## Reconcile

`reconcile` классифицирует current и historical portable skills, package
commands, plugins, agents и installation metadata одного scope:

```shell
npx --yes @kisev/skills-opencode@latest reconcile --scope project --dry-run
npx --yes @kisev/skills-opencode@latest reconcile --scope project --confirm <digest>
npx --yes @kisev/skills-opencode@latest reconcile --scope global --dry-run --json
```

Перед reconcile сначала обновите package в принадлежащем ему npm project и
примените exact installer plan. Reconcile не устанавливает, не обновляет и не
удаляет portable skills; для них используйте только stable
`npx --yes skills@latest` с `https://kisev.github.io/skills`.

Confirmed reconcile архивирует exact-owned retired assets в private
content-addressed XDG archive и удаляет их deployed copies. Modified, user-owned,
unknown, symlink, unsafe и ambiguous entries остаются без изменений как findings
или conflicts. Worktrees и runtime state сохраняются. Archive доступен для
просмотра через `doctor`; команд restore или purge нет.

## Управление agents

Direct CLI управляет models fixed agents и additional critics без LLM call:

```shell
npx --yes @kisev/skills-opencode@latest agent list --scope global
npx --yes @kisev/skills-opencode@latest agent configure manager --scope global --dry-run
npx --yes @kisev/skills-opencode@latest agent model-set worker --scope global --model openai/gpt-5 --variant high --dry-run
npx --yes @kisev/skills-opencode@latest critic add security --scope global --model anthropic/claude-sonnet-4-6 --dry-run
npx --yes @kisev/skills-opencode@latest agent reconcile --scope global --dry-run
```

Fixed roles сохраняют имена, prompts и permissions; меняются только model и
variant. Additional critics используют `critic-<safe-suffix>`. Каждая mutation
использует тот же contract preview и one-time confirmation.

## Uninstall

Package должен оставаться доступным до удаления его assets:

1. Покажите preview и подтвердите удаление package-owned assets.
2. Удалите `@kisev/skills-opencode` из user-owned массива `plugin`.
3. Удалите dependency из того же npm project.
4. Перезапустите OpenCode.

```shell
npx --yes @kisev/skills-opencode@latest uninstall --scope project --dry-run
npx --yes @kisev/skills-opencode@latest uninstall --scope project --confirm <digest>
npm uninstall @kisev/skills-opencode
```

Для global scope запустите stable npx-команду из любого каталога с
`--scope global`, затем удалите dependency из persistent npm project в
`~/.config/opencode`. Uninstall архивирует exact manifest-owned assets и
сохраняет modified files как conflicts вместе с worktrees, runtime state и
retained profile configuration. Он не удаляет portable skills и не меняет
`opencode.json`. Команд restore или purge для archive нет.

## Границы

- Portable skills и package assets устанавливаются, обновляются и удаляются
  независимо.
- Commands, соответствующие skills, являются thin adapters; portable skill
  остаётся authoritative и устанавливается отдельно.
- Package tools: `capabilities`, `route`, `doctor`, `agent_profiles`, `reconcile`;
  у `route` нет slash command.
- Global scope не зависит от cwd; project scope использует `.opencode` в текущем
  каталоге.
- Installer владеет только files с доказанными manifests и exact hashes.
- Package распространяется по лицензии MIT. Текущий inventory и checks описаны в
  [инвентаре миграции](../migration-inventory.md) и
  [документе проверки](../verification.md).
