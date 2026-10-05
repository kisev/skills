---
skill: code-review
title: Ревью локальных изменений перед push
order: 10
prompt: |
  Проверь мои изменения в рабочем дереве, прежде чем я сделаю push.
steps:
  - title: Читает незакоммиченный diff
    detail: |
      Собирает картину рабочего дерева из `git status` и `git diff`,
      сопоставляя каждый hunk с файлами и поведением, которые он затрагивает.
  - title: Проверяет поведение, а не стиль
    detail: |
      Ищет конкретные риски: обработку ошибок, конкурентность, валидацию
      входных данных, совместимость и отсутствие регрессионного покрытия.
  - title: Возвращает вердикт с находками
    detail: |
      У каждой находки есть серьёзность и минимальное исправление; ревью
      остаётся read-only и ничего не меняет.
artifacts:
  - label: Отчёт ревью (фрагмент)
    language: markdown
    content: |
      ## Findings

      1. **major** - `flushQueue()` swallows rejections: the `catch` block logs
         and continues, so a failed delivery is retried forever. Apply backoff
         and surface the failure to the caller.
      2. **minor** - `MAX_RETRIES` is read at module load, so tests cannot
         shrink it. Read it inside `deliver()` or inject it.

      ## Verdict

      Request changes: fix the retry loop before pushing; the test hook is
      recommended but optional.
limitations: Только чтение. Ревьюит одно рабочее дерево или один merge request за раз и никогда не правит код, не ставит файлы в staged и не делает push.
---

Ревьюер держится согласованной области: помечает риски самого изменения,
а принятые ранее решения фиксирует как follow-up, а не блокирует на них.
