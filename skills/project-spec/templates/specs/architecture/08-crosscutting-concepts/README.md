# 08. Сквозные концепции

## Назначение

Опиши общие principles и mechanisms, действующие в нескольких building blocks.

## Сюда относится

- error handling, logging и configuration;
- security, authentication и observability;
- persistence, concurrency и dependency management;
- другие подтверждённые cross-cutting rules.

## Сюда не относится

- локальная деталь реализации одного component;
- список возможных concepts на будущее;
- нормативные цели качества без описания mechanism.

## Правила декомпозиции

README содержит overview и индекс. Один дополнительный файл соответствует одному
реальному principle или mechanism, который затрагивает несколько blocks.

## Ожидаемая структура

```text
08-crosscutting-concepts/
├── README.md
└── <crosscutting-concept>.md
```

## Шаблон содержания

Для каждого concept укажи scope, rules, participating blocks, failure behavior и
связанные requirements/ADR. Не создавай файл, если mechanism локален.
