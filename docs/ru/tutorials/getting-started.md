# Начало работы с portable skills

[English](../../tutorials/getting-started.md)

Этот tutorial устанавливает текущую stable distribution portable skills для
Codex и OpenCode. Одна canonical global copy будет доступна обоим host.

## Перед началом

Нужен Codex, OpenCode или оба host, а также окружение с доступным `npx`. Команда
использует stable channel installer и читает поддерживаемую distribution GitHub
Pages, а не authored repository.

## 1. Установите skills

Запустите:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent opencode --agent codex --skill '*' --copy --global --yes
```

Команда устанавливает текущую stable distribution в `~/.agents/skills`.
`--copy` сохраняет одну canonical copy для обоих выбранных host. Установленную
distribution идентифицируют release metadata и archive digests.

Если вы используете только один host, оставьте только его agent option:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent codex --skill '*' --copy --global --yes
```

или:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent opencode --skill '*' --copy --global --yes
```

## 2. Проверьте установку

Выведите список установленных global skills:

```shell
npx --yes skills@latest list --global
```

Если выбранный host работал во время установки, перезапустите его. После этого
установленные skills должны быть доступны из `~/.agents/skills`.

## 3. Решите, нужен ли вам skills-opencode

Portable skills уже работают в OpenCode. Устанавливайте
`@kisev/skills-opencode`, только если также нужны OpenCode-specific commands,
fixed agents, routing tools, диагностика или optional plugin wrappers. У package
отдельный lifecycle, и он не устанавливает portable skills.

Для этого optional layer следуйте [инструкции по интеграции
OpenCode](../how-to/opencode-integration.md). Для project-scoped installation,
обновления или очистки используйте [how-to по portable
skills](../how-to/portable-skills.md).
