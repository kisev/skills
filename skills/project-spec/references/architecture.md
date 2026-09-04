# Профиль архитектуры

Используй taxonomy arc42 без заявления формального соответствия. Все 12 разделов
существуют сразу: цели, ограничения, контекст, стратегия, building blocks,
runtime, deployment, cross-cutting concepts, решения, качество, риски и
глоссарий.

Дополнительные файлы допустимы только в `05-building-block-view` для реального
компонента, в `06-runtime-view` для значимого end-to-end сценария, в
`08-crosscutting-concepts` для механизма нескольких компонентов и в
`09-architecture-decisions` для одного ADR. Корневой `README.md` каждого раздела
остается индексом. Не дроби архитектуру по feature и не создавай `misc.md`.

Диаграммы используй только когда они делают текст понятнее: совместимые Mermaid
`flowchart`, `sequenceDiagram` или `stateDiagram`. System Context уместен в 03,
Container/Component в 05, Dynamic в 06 и Deployment в 07.
