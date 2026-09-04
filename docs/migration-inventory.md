# Инвентарь миграции

Этот инвентарь фиксирует запланированное разделение Bedrock-managed bundle.
На этом этапе в репозитории реализован только `askme`.

| Инвентарь | Количество | Назначение | Статус |
| --- | ---: | --- | --- |
| Portable skills | 23 | `skills/` | Запланировано; `askme` - canary |
| OpenCode-specific skills | 7 | необязательная интеграция OpenCode | Запланировано |

Portable inventory не должен наследовать Bedrock runtime state, catalog files,
providers или имена инструментов OpenCode. `agent-profiles`, `capabilities`,
`doctor` и `bedrock` заменяются возможностями host или package либо удаляются;
они не являются portable skills этого репозитория.

Commands становятся тонкими OpenCode adapters. Они выбирают или вызывают
portable skill, но не реализуют второй workflow. OpenCode agents и plugins
поставляются будущим необязательным npm package, а не установкой skill.

В рамках этой миграции намеренно не реализуются остальные skills, npm package,
agents, commands и plugins.
