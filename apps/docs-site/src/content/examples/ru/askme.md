---
skill: askme
title: Уточнение расплывчатого запроса на функцию
order: 10
prompt: |
  Добавь пагинацию в эндпоинт пользователей.
steps:
  - title: Сначала проверяет репозиторий
    detail: |
      Находит готовый list-хелпер с offset-пагинацией и правило проекта не
      дублировать общие утилиты, поэтому вопрос реализации снимается
      осмотром, а не вопросом пользователю.
  - title: Строит дерево решений
    detail: |
      Осталось одно решение, меняющее публичный контракт API: политика
      размера страницы.
  - title: Задаёт минимальный полезный вопрос
    detail: Один вопрос, варианты с конкретными эффектами, рекомендация - и ожидание ответа.
artifacts:
  - label: Вопрос интервью (в чате)
    language: markdown
    content: |
      **Page size policy** - the endpoint returns up to 50 items today, and
      the choice locks the public contract:

      - **Server-fixed, 50 (Recommended)** - no client parameter to validate
        or document; changing the size later stays a backward-compatible bump.
      - **Client-controlled, 1-100** - flexible for power clients, but you own
        validation, caps, and documentation of every misuse.

      Which policy should the endpoint implement?
limitations: Спрашивает только то, что нельзя установить осмотром; интервью завершается границей решения и само ничего не реализует.
---

Скилл снимает минимум необходимого: выбор хелпера не дошёл до пользователя,
потому что репозиторий уже ответил на этот вопрос.
