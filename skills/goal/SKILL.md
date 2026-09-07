---
name: goal
description: Сформировать проверяемую read-only цель в portable формате work-item/v1.
license: MIT
compatibility: Requires an Agent Skills host with native Question support; no runtime or state is required.
allowed-tools: native Question
metadata:
  author: "Kirill Sevriugin"
  version: "1.1.1"
---

# Goal

Прочитай `references/work-item-contract.md` и сформируй цель, которую можно
скопировать в другую систему. Этот skill строго read-only: не создавай и не изменяй файлы,
XDG state, repository, session, receipts или внешние системы.
OpenChamber Goal Mode как внешний способ выполнения цели не является частью этого
skill.

## Исследование

Сначала исследуй доступные факты: запрос пользователя, открытые файлы, состояние
репозитория, доступные проверки и явно названные ограничения. Не выдавай
предположение за факт; неизвестное внеси в `unresolved_questions` или blocker.
Задавай через native Question только вопросы, ответы на которые меняют problem,
outcome, scope, acceptance criteria, dependency, safety или stop condition.
Если фактов достаточно, вопросов не задавай.

Для сложной задачи или явного запроса выполни один optional independent premortem
до итоговой формулировки: максимум три риска с probability, impact и
предлагаемой правкой формулировки. Premortem-agent не редактирует item; решение
по каждому риску принимает основной агент. Если независимый агент недоступен,
статус premortem равен `skipped`; при независимом проходе статус равен
`completed`. Не имитируй self-review.

## Output contract

Выводи один готовый для копирования компактный JSON-объект именно
`work-item/v1`, без дополнительных полей, markdown-обёртки и служебного текста.
Он обязан содержать `contract_version`, `item_id`, `problem`, `outcome`,
`acceptance_criteria`, `scope.in_scope`, `scope.non_goals`, `dependencies`,
`external_actions`, `assumptions`, `safety.constraints`,
`safety.operational_constraints`, `risks`, `unresolved_questions` и
`stop_conditions`. Каждый criterion содержит проверяемые `statement`, минимум
один конкретный `evidence` и ссылки `dependencies`; dependencies образуют DAG.
В `acceptance_criteria` явно включи проверку результата и формат отчёта: краткий
status (`completed`/`blocked`), факты/evidence по каждому criterion, checks,
unresolved items и следующий безопасный шаг. Не включай acceptance criterion,
который нельзя проверить.

Готовый item имеет не более 3000 символов, verdict `ready` и пустой
`unresolved_questions` для blocking-вопросов. Если обязательный факт неизвестен,
верни тот же полный `work-item/v1` item с `unresolved_questions` и stop condition,
делающими blocker явным; не заполняй неизвестное выдуманными данными. Повторный
вызов с теми же фактами и вводом должен дать байт-в-байт тот же JSON: стабильный
`item_id`, порядок массивов и compact JSON обязательны. Machine rules можно
проверить через materialized `scripts/work_item.py validate`, но это не разрешает
писать state и не превращает semantic assessment в машинную эвристику.
