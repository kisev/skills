---
skill: commit-msg
title: Одно сообщение для разнородных staged-изменений
order: 10
prompt: |
  Посмотри мои staged-изменения и напиши сообщение коммита.
steps:
  - title: Изучает diff и недавнюю историю
    detail: |
      Запускает `git diff --cached --stat` и `git log --oneline -8`, чтобы
      понять, что изменилось и какие соглашения уже приняты в репозитории.
  - title: Составляет subject по главной части изменения
    detail: |
      Diff затрагивает одну функцию парсера и её регрессионные тесты, поэтому
      в subject попадает исправление поведения, а не перечисление файлов.
  - title: Только печатает сообщение
    detail: Скилл никогда не выполняет `git commit` — он печатает сообщение на проверку.
artifacts:
  - label: Сообщение коммита (вывод в терминал)
    language: text
    content: |
      fix: tolerate empty frontmatter blocks in skill sources

      Trim leading document separators before YAML parsing so a source file
      that starts with a comment-only header still validates, and cover the
      case with a parser regression test.
limitations: Даёт одно сообщение за вызов и никогда не создаёт коммит сам. Только сообщения коммитов; описания merge request — вне области скилла.
---

В этом примере репозиторий ведёт линейную историю с subjects `fix:` и `feat:`
короче 72 символов, поэтому скилл подстраивается под доминирующее соглашение,
а не изобретает собственный формат.
