# 05. Представление building blocks

## Назначение

Опиши статическую архитектурную декомпозицию системы.

## Сюда относится

- subsystems, services, components, modules и layers;
- responsibilities и dependencies;
- основные внутренние и внешние interfaces;
- диаграммы Container/Component, если они полезны.

## Сюда не относится

- feature backlog;
- runtime-последовательности;
- история решений и декомпозиция задач.

## Правила декомпозиции

README содержит overview и индекс. Дополнительный файл разрешён только для
реального building block с самостоятельной архитектурной ответственностью. Не
создавай blocks по features и не дроби файл только из-за размера.

## Ожидаемая структура

```text
05-building-block-view/
├── README.md
└── <real-building-block>.md
```

## Шаблон содержания

Для каждого block укажи responsibility, boundary, dependencies и interfaces.
Дополнительные файлы перечисли в README; при простой системе оставь всё здесь.
