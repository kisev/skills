# Профиль архитектуры

Используй arc42 как taxonomy, но не заявляй формальное соответствие arc42, C4 или
ISO. Все 12 разделов существуют сразу.

## Разделы

1. `01-introduction-and-goals` - назначение, заинтересованные стороны, цели и
   обзор требований.
2. `02-architecture-constraints` - архитектурные последствия `REQ-C-*`, а не
   второй нормативный список ограничений.
3. `03-context-and-scope` - граница, пользователи, соседние системы, внешние
   зависимости и взаимодействия.
4. `04-solution-strategy` - ключевые технологии, декомпозиция, patterns и способы
   достижения критичных целей качества.
5. `05-building-block-view` - статическая структура, responsibilities,
   dependencies и interfaces.
6. `06-runtime-view` - значимые end-to-end scenarios, data/control flow, errors,
   recovery и asynchronous behavior.
7. `07-deployment-view` - runtime environment, deployment units, infrastructure,
   network, storage и относящийся CI/CD.
8. `08-crosscutting-concepts` - общие mechanisms: errors, logging, configuration,
   security, observability, persistence, concurrency и другие.
9. `09-architecture-decisions` - индекс ADR и сами ADR.
10. `10-quality-requirements` - как architecture обеспечивает `REQ-Q-*`, а не
    дублирование нормативных требований к качеству.
11. `11-risks-and-technical-debt` - известные risks, debt, хрупкие области и
    дорогие изменения, но не backlog.
12. `12-glossary` - неоднозначные и специфичные для проекта terms, но не словарь
    общеизвестных технологий.

## Декомпозиция

Дополнительные Markdown-файлы разрешены только в четырёх местах:

- `05-building-block-view`: один файл на реальный subsystem, service, component,
  module, layer или package с самостоятельной responsibility;
- `06-runtime-view`: один файл на значимый end-to-end runtime scenario;
- `08-crosscutting-concepts`: один файл на principle или mechanism, который
  затрагивает несколько building blocks;
- `09-architecture-decisions`: один файл на один ADR.

Не дроби architecture по feature и не создавай `part-1.md`, `misc.md`, `other.md`
или похожие файлы. Корневой `README.md` каждого раздела остаётся главным документом
и индексом дополнительных файлов.

## Диаграммы

Используй C4 concepts внутри arc42: System Context в 03, Container/Component в 05,
Dynamic в 06, Deployment в 07. Не требуй все уровни. Диаграммы храни в Markdown как
широко поддерживаемые Mermaid `flowchart`, `sequenceDiagram` или `stateDiagram`.
Не используй experimental C4 notation и не создавай диаграмму, если текст понятнее.
