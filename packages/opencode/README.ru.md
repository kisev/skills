# Интеграция OpenCode

[English](README.md)

`@kisev/skills-opencode` - полноценный OpenCode-specific компонент Agent
Skills. Он дополняет portable skills, но имеет собственный lifecycle установки,
обновления и удаления.

## Что добавляет package

- OpenCode slash-command adapters для установленных portable skills и package tools.
- Шесть fixed agents: `manager`, `architect`, `mapper`, `worker`, `review` и
  `critic`.
- Capability routing, doctor, reconcile и управление agent profiles.
- Optional plugin wrappers `rules-injector`, `rtk` и `zed-bell`.

Package не содержит, не устанавливает, не обновляет и не удаляет portable skills.

## Требования

- Node.js 22 или новее.
- OpenCode `>=1.18.29 <1.19.0`.
- Постоянный npm project, которому принадлежит dependency.

## Project installation

Установите package в npm project репозитория и покажите preview managed assets:

```shell
npm install --save-exact @kisev/skills-opencode
npx --yes @kisev/skills-opencode@latest install --scope project --dry-run
```

Выполните exact confirmation command из preview. Если выбранным assets нужна core
integration, добавьте package в user-owned configuration OpenCode, сохранив
существующие entries:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@kisev/skills-opencode"]
}
```

После activation или изменения assets перезапустите OpenCode. Installer не
меняет `opencode.json`, а выбор command adapters не устанавливает portable skills.

## Документация

Каноническая документация находится в `docs/`, а не в исходниках package:

- [Полная инструкция по интеграции OpenCode](https://github.com/kisev/skills/blob/main/docs/ru/how-to/opencode-integration.md)
- [Инструкция по portable skills](https://github.com/kisev/skills/blob/main/docs/ru/how-to/portable-skills.md)
- [Индекс документации](https://github.com/kisev/skills/blob/main/docs/ru/README.md)

Полная инструкция описывает global installation, выбор assets, confirmation,
activation, doctor, update, reconcile, agent profiles, ownership и uninstall.
