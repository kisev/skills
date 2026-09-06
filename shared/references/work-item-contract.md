# Общий work item contract

Версия контракта: `work-item/v1`.

Все четыре workflow используют один нормализованный work item. Canonical schema и
stdlib-only validator находятся рядом с этим документом; установленный skill
получает их materialized-копию и во время выполнения не обращается к `shared/`.

## Нормализованная структура

Обязательны `problem` и описанный конечный `outcome`; `acceptance_criteria` содержит
проверяемые statements, ссылки на `evidence` и зависимости критериев. `scope`
разделяет `in_scope` и явные `non_goals`. Далее указываются `dependencies`,
`external_actions`, `assumptions`, `safety` с operational constraints, `risks`,
`unresolved_questions` и `stop_conditions`.

Каждый dependency имеет стабильный `id`, статус `available`, `pending` или
`blocked`, и список `depends_on`. Ссылки должны существовать, а граф должен быть
DAG. Evidence описывается до начала выполнения, а не заменяется журналом шагов.

## Единая оценка

`scripts/work_item.py validate --input ITEM.json [--semantic SEMANTIC.json]`
возвращает JSON report и определённый exit code. `machine_findings` проверяет
schema, обязательные поля, уникальность и ссылки, границы, достижимость и циклы.
`semantic_assessment` содержит structured findings независимого feasibility/
consistency агента; validator не выдаёт машинную эвристику за смысловую оценку.

Порядок findings детерминирован: `severity`, `code`, `path`, `message`. Для
неизменного item и evidence повторная проверка возвращает тот же report и digest.
Единые verdicts: `ready`, `needs_clarification`, `blocked`.

## Обязанности workflow

- `askme` задаёт только вопросы, меняющие поля контракта, и завершает
  `normalized_item` либо возвращает явный `blocker`.
- `task-prepare` не создаёт publication artifact до verdict `ready`; GitLab
  mutations запрещены.
- `task-review` возвращает один из трёх verdicts, findings с evidence и
  рекомендуемыми изменениями; он не проверяет реализацию.
- `goal` не переводит invalid item в `running`, а terminal completion связывает
  каждое criterion с evidence. Persisted state читает совместимо и не теряет
  старые поля или GitLab artifacts.

## Optional premortem

Для сложной задачи или явного запроса до выполнения допускается ровно один
независимый проход. Он возвращает не более трёх причин провала с `probability`,
`impact` и `proposed_wording_change`. Premortem-agent не редактирует item.
Основной агент отдельно принимает или отклоняет каждое предложение с причиной.
Без независимого агента результат равен `skipped`, self-review не имитируется и
workflow не блокируется.
