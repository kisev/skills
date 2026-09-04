# 06. Выполнение во времени

## Назначение

Опиши значимые end-to-end runtime scenarios системы.

## Сюда относится

- последовательности interactions;
- data/control flow;
- errors, recovery и asynchronous behavior;
- переходы lifecycle, важные для понимания системы.

## Сюда не относится

- каждый function call;
- статический каталог компонентов;
- малозначимые happy-path примеры.

## Правила декомпозиции

README содержит overview и индекс. Один дополнительный файл соответствует одному
важному end-to-end scenario. Не дроби по отдельным функциям.

## Ожидаемая структура

```text
06-runtime-view/
├── README.md
└── <significant-scenario>.md
```

## Шаблон содержания

Для каждого scenario укажи trigger, participants, основной flow, failures и
recovery. При необходимости используй Mermaid `sequenceDiagram` или `stateDiagram`.
