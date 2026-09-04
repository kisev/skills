# Аудит спецификации

Аудит полностью read-only. Он независимо проверяет качество canonical documents и
их соответствие исходному коду, тестам, схемам, configuration, CLI/API, CI и
deployment. Ничего не исправляй и не создавай файлы отчёта.

## Порядок

1. Определи scope. Без аргумента проверь полный canonical `specs/`. С path,
   `REQ-*`, `ADR-*` или описанной областью проверь выбранный объект, связанные
   requirements, architecture/ADR и необходимое repository evidence.
2. Проверь внутреннее качество и согласованность requirements, architecture и ADR
   по профилям ниже.
3. Отдельно проверь drift между canonical specification и repository evidence.
4. Сначала выведи ранжированные замечания качества, затем drift statuses и
   непроверенные границы. Не смешивай дефект документа со статусом drift.

В начале результата явно укажи `Scope: full` или точную ограниченную область. Для
focused audit перечисли непроверенные границы. Разрешён `OK` только с явной
пометкой `Scope: <scope>`; не заявляй project-wide полноту или project-wide `OK`.

## Качество requirements

Проверь цели и non-scope, термины, входы и выходы, observable behavior, invariants,
edge cases, failure behavior, unsupported behavior, security, compatibility и
verification. Нормативные требования по возможности атомарны, однозначны,
необходимы, непротиворечивы, проверяемы и трассируемы. Проверь стабильность
`REQ-*` IDs, ссылки на machine-readable contracts и отсутствие дублирования их
синтаксиса.

Не требуй искусственную EARS-форму или rationale для тривиального требования. Не
считай implementation detail дефектом, если она не меняет observable contract или
архитектурный invariant.

## Качество architecture

Проверь согласованность 12 viewpoints между собой и с requirements:

- system boundary, заинтересованные стороны, context и scope;
- responsibilities и реальные boundaries building blocks;
- направление dependencies, interfaces, ownership и locality;
- runtime flows, lifecycle, concurrency, failures и recovery;
- deployment, trust boundaries, security и observability;
- mechanisms, обеспечивающие quality requirements;
- compatibility, migration, testability, risks и technical debt;
- feasibility с учётом repository constraints и применимые migration,
  rollout/rollback mechanisms.

Абстракция оправдана только реальной responsibility или boundary. Не выдавай
вкусовое предпочтение, потенциальное улучшение или непроверенный будущий design за
дефект. Не требуй диаграмму, если она не делает architecture понятнее.

## Качество ADR

Для каждого ADR проверь architectural significance, context, decision drivers,
существенно разные considered options, обоснование outcome, положительные и
отрицательные consequences, status, date, reversibility, compatibility, risks,
связанные requirements/ADR и supersession. Старый ADR не должен быть переписан так,
будто новое решение существовало всегда; замена требует нового ADR и явных связей.

Проверь, что ADR не используется для bugfix или тривиальной implementation detail,
а значимое решение не осталось только неявным текстом в architecture.

## Замечания качества

Сообщай только подтверждённые проблемы. Ранжируй их по критичности, влиянию и
неопределённости. Для каждой укажи критичность, точный path и section или
requirement/ADR ID, repository evidence либо внутреннее противоречие документов,
последствие и минимальное исправление canonical specification.

Если замечаний качества нет, явно сообщи об этом. Не называй отсутствие repository
evidence дефектом качества, когда правильный drift status - `SPEC_AHEAD` или
`UNKNOWN`.

## Drift statuses

- `OK`: specification подтверждается implementation/evidence.
- `SPEC_AHEAD`: specification требует поведение или свойство, которое evidence не
  подтверждает.
- `IMPLEMENTATION_AHEAD`: implementation содержит значимое observable behavior или
  architectural change, отсутствующее в canonical specs.
- `CONFLICT`: repository sources противоречат друг другу.
- `UNKNOWN`: достоверная автоматическая проверка невозможна; не угадывай.

## Drift evidence

Для каждого отклонения укажи status, requirement ID при наличии, path в spec,
source file, symbol/function/class/config path, test/schema/CI evidence и краткое
объяснение влияния. Не объявляй отсутствие упоминания drift без проверяемого
observable или architectural consequence.

Если drift отсутствует, сообщи `OK` независимо от наличия замечаний качества.
Перечисли существенные непроверенные границы как `UNKNOWN`. Результат выводи только
в conversation. Человек сам решает, исправлять код под spec или менять spec через
`spec-update`.
