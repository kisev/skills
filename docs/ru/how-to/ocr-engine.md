---
audience: user
review: {"components": ["reviewmatic"], "sources": ["apps/reviewmatic/src/reviewmatic/ocr.py", "apps/reviewmatic/src/reviewmatic/background.py", "apps/reviewmatic/src/reviewmatic/profiles.py", "apps/reviewmatic/src/reviewmatic/cli.py", "apps/reviewmatic/tests/test_ocr.py", "apps/reviewmatic/tests/test_profiles.py"], "contracts": ["specs/capabilities/skills/mr-review.md", "skills/mr-review/references/run-path.md"]}
---

# Запуск движка OpenCodeReview

[English](../../how-to/ocr-engine.md)

CLI OpenCodeReview (`ocr`) — единственный движок ревью в `mr-review`. Он читает
diff, отправляет его настроенной LLM и возвращает находки в JSON. Навык не
запускает внутренних критиков и арбитра.

## Установка и версия

Протестированный минимум — 1.13.6. Установите или обновите:

```shell
npm install -g @alibaba-group/open-code-review@latest
```

Файл `references/requirements.json` навыка содержит ту же команду установки в
записи `ocr` вместе с командой проверки `ocr version`. Если версия ниже,
рантайм останавливается с указанием обновиться.

## Выбор ревьюеров

Задайте алиасы глобально в `~/.reviewmatic/reviewers.json` и локально в
`./.reviewmatic/reviewers.json`; локальный файл перекрывает глобальный по
алиасу и умолчанию:

```json
{
  "default": "fast",
  "reviewers": [
    {"alias": "fast", "provider": "openai", "model": "gpt-5", "effort": "medium"},
    {"alias": "deep", "provider": "anthropic", "model": "claude-opus-5", "effort": "high"}
  ]
}
```

Разрешены только `alias`, `provider`, `model` и `effort`; никогда не пишите
учётные данные в профиль. Эффективный профиль и проверку провайдеров печатает
`reviewmatic profiles`. Проверка сверяет имена с `ocr llm providers`; свои
провайдеры настраиваются только в конфигурации OCR, которую навык не читает.

Без профиля используйте умолчание OCR или разовые provider и model.

## Фоновый файл

Менеджер пишет цель задачи, критерии приёмки, ограничения, открытые вопросы и
разделы контекста в JSON, а рантайм укладывает их в лимит 8000 байт:

```shell
reviewmatic background --input .reviewmatic/background.json --output .reviewmatic/background.md
```

Задача идёт первой. Каждый сокращённый раздел назван в напечатанном
результате, а исполняемый файл — измеренный.

## Прогон и объединение

```shell
reviewmatic ocr-runs --repo <checkout> --from <start-sha> --to <head-sha> --background .reviewmatic/background.md --reviewers fast,deep --output-dir .reviewmatic/ocr
```

Каждый алиас запускает свой процесс `ocr review` со своим выводом; несколько
алиасов идут параллельно. Разовый прогон использует `--provider` и `--model`
вместо `--reviewers`. Неудачный прогон сообщает код выхода и останавливает
ревью; менеджер не подменяет его своим ревью.

Когда выбрано несколько прогонов, менеджер объединяет дубли и конфликты и
записывает каждую причину. Ни одна находка не теряется молча.

## Сессии и инкрементальность

Каждый прогон сохраняет сессию. Повторное ревью — свежий прогон плюс:

```shell
reviewmatic ocr-compare --before <previous-session> --after <current-session> --repo <checkout>
```

Сравнение группирует находки как новые, сохраняющиеся, решённые и
непросмотренные. Группировка — вспомогательный контекст runbook; вердикт
опирается на текущий прогон. `ocr review --resume <session-id>` продолжает
прерванный прогон.

## Публикация

Runbook заканчивается одним неинтерактивным блоком черновиков, который
генерирует `reviewmatic drafts`. Он начинается с проверки головы относительно
проверенной ревизии и создаёт только черновики GitLab. Человек правит и
публикует их в UI GitLab; команды публикации нет.
