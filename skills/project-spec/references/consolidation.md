# Консолидация канонической спецификации

Консолидация - обязательная часть каждого `spec-update`, а не отдельный
периодический проект. Её цель - сохранить `specs/` компактной моделью текущей
системы, которую человек способен прочитать и удержать в голове. Git хранит
историю; canonical documents не являются журналом изменений.

## Scope

Обычный `spec-update` проверяет затронутые documents, requirements, ADR и
viewpoints, на которые влияет запрос. Не расширяй scope без необходимости.

Явный запрос человека на консолидацию specification требует штатного вопроса:
согласуй ограниченную область либо полный `specs/`. Полную specification не
исследуй и не переписывай по умолчанию.

## Анализ

До preview проверь, не требует ли затронутая область одного из изменений:

- объединить две нормативные формулировки одного contract в одну canonical точку и
  заменить повтор ссылкой;
- удалить отменённое requirement, временный implementation plan или описание
  поведения, которого больше нет в согласованном target state;
- убрать детали, не влияющие на observable contract или architectural invariant,
  если они мешают пониманию; сохранить необходимую причинность и ссылку;
- исправить ссылку на удалённый path, устаревший `REQ-*`/`ADR-*` или отменённый
  interface;
- заменить изменённое архитектурное решение новым ADR с явной supersession, а не
  переписывать accepted ADR так, будто прежнего решения не существовало.

Не удаляй current non-scope, подтверждённый risk, границу совместимости или
необходимое explanation только ради краткости. Не создавай archive, version,
changelog, plan, delta или иной постоянный workflow artifact внутри `specs/`.

## Preview и подтверждение

До показа diff явно добавь результат:

```text
Consolidation: required
Scope: requirements/interfaces/cli.md and architecture/06-runtime-view
Changes: remove superseded apply wording; retain ADR-0001 as history;
add one canonical reference.
```

Либо:

```text
Consolidation: not required
Scope: requirements/interfaces/cli.md
Reason: the requested contract is new and has no duplicate or superseded wording.
```

При `required` preview обязан содержать и предметное изменение, и обоснованные
simplification edits. При `not required` preview не должен придумывать чистку. В
обоих случаях сначала получи подтверждение точного diff.

## Завершение

После изменения в проверенной области нет конкурирующих canonical documents для
одного interface или constraint, отменённой нормы, дублирующей формулировки и битой
ссылки. Если evidence недостаточно, задай вопрос; не удаляй текст на основании
предположения.
