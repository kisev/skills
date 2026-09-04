# Адаптивное интервью

Интервью закрывает смысловые пробелы, а не воспроизводит фиксированную анкету.

## Процесс

1. Собери известные факты и решения.
2. Найди assumptions, gaps и contradictions.
3. Задай от одного до пяти наиболее важных связанных вопросов через штатный
   интерактивный механизм host; при его отсутствии задай вопросы в чате.
4. Проанализируй ответы и повторяй, пока целевое состояние не станет однозначным.
5. Перед preview выполни readiness check в контексте; не создавай checklist или
   другой repository artifact.

Не спрашивай то, что надёжно следует из evidence или предыдущих ответов. Особое
внимание уделяй edge cases, failure behavior, compatibility, unsupported behavior,
invariants, security boundaries и lifecycle/state transitions.

## Readiness check

Интервью готово к preview, когда одновременно выполняются условия:

- значимые contradictions разрешены или явно оставлены как `UNKNOWN` человеком;
- critical unknowns по behavior, architecture, compatibility, security и quality
  отсутствуют либо человек явно принял их как границу specification;
- scope и explicit non-scope определены;
- основные behaviours, failure behavior, invariants и unsupported behavior
  сформулированы однозначно;
- external interfaces и compatibility guarantees определены либо явно
  неприменимы;
- verification для нетривиальных нормативных требований понятна;
- architecture, runtime и deployment описаны настолько, насколько это нужно для
  согласованного целевого состояния;
- terminology не содержит значимых неразрешённых трактовок.

Если хотя бы один пункт не выполнен, продолжи адаптивное интервью. Не используй
readiness check как фиксированную анкету для пользователя и не показывай служебный
checklist вместо содержательных вопросов.

## Области greenfield-интервью

Покрой применимые области: проблема, цель, пользователи, заинтересованные стороны,
scope, explicit non-scope, ключевое поведение, external interfaces, constraints,
compatibility, quality attributes, security, architecture, integrations, runtime,
deployment, verification, risks и terminology.

Для неприменимой области зафиксируй краткую причину в соответствующем canonical
document. Не придумывай содержание только для заполнения раздела.
