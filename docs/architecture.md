# Архитектура

## Источник истины

Единственный canonical checkout сопровождающего находится в
`/home/kisev/Projects/Github/kisev/skills`. Другие локальные копии не являются
источником изменений или установки.

Переносимые skills находятся в `skills/<name>/` и являются законченными
единицами установки. Во время работы skill может использовать только файлы под
собственным корнем. `shared/` - входные данные сопровождающего, а не runtime-
зависимость установленного skill. `scripts/sync_shared.py` создаёт точные копии
по manifest, а эти копии хранятся в Git под соответствующими skills.

В репозитории нет пользовательского CLI. Maintainer scripts могут использовать
только Python stdlib; Python runners, если они нужны skill, находятся внутри
этого skill.

## Интеграция с host

Переносимые skills описывают задачу и не требуют конкретного host. Host может
предоставить штатный инструмент интерактивных вопросов; если его нет, agent
задаёт вопрос в чате. OpenCode-only adapters, agents, commands, plugins и
capability router относятся к необязательному package `packages/opencode/` и не
нужны для установки или работы portable skill. Package не содержит копий skills.
Его явный installer materialize-ит assets после dry-run и matching digest;
upgrade/uninstall сохраняют user drift через ownership manifest. Stateful plugins
являются opt-in и при отключении не создают state, timers, sessions или mutations.

## OpenCode runtime

Семь specialized skills устанавливаются как обычные self-contained Agent Skills.
Их Python runner materialize-ит общий stdlib runtime внутрь skill и использует
только XDG/OpenCode user-owned config/state. Package runtime не ссылается на
checkout и экспортирует восемь независимых plugin factories. `capabilities`,
`route` и `doctor` являются package tools и read-only command replacements;
они не устанавливают, не исправляют и не управляют agent profiles.

## Инварианты materialization

- JSON manifest - единственное отображение общих исходников в пути skills,
  включая minimal Python runtime для автономных runner-ов.
- Пути относительные, нормализованные и ограничены соответственно каталогами
  `shared/references/` и `skills/`.
- Symlinks в исходных и конечных путях отклоняются.
- Нормализация и чтение всех исходников выполняются до записи.
- Подготовленные файлы заменяются атомарно; при ошибке замены выполняется
  откат.
- `--check` работает только на чтение и сообщает о drift ненулевым exit status.
