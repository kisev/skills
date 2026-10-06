---
audience: user
review: {"components": ["reviewmatic"], "sources": ["apps/reviewmatic/src/reviewmatic/ocr_critic.py", "apps/reviewmatic/src/reviewmatic/draft.py", "apps/reviewmatic/src/reviewmatic/local_review.py", "apps/reviewmatic/src/reviewmatic/cli.py", "apps/reviewmatic/tests/test_ocr_critic.py"], "contracts": ["specs/capabilities/skills/code-review.md", "skills/code-review/references/workflow.md"]}
---

# Запуск OCR-критика в панели ревью

[English](../../how-to/ocr-critic.md)

CLI OpenCodeReview (`ocr`) может входить в панель ревью как механический критик
вместе с модельными или вместо них. Он ревьюит ту же записанную изменения,
отчитывается находками в одну квитанцию критика, и арбитр выносит вердикт по
его находкам так же, как по находкам любого модельного критика. OCR никогда не
отвечает на вопросы, назначенные критикам.

## Выбор состава

Запишите панель как обычно через `reviewmatic record-participants` и пометьте
OCR-критика полем `engine`:

```json
{
  "critics": [
    {"name": "ocr-critic", "engine": "ocr"},
    {"name": "critic-general", "profile": "critic-general"}
  ],
  "arbitrator": {"name": "arb-main"}
}
```

Закрепите LLM за запуском флагами команды; без них OCR CLI использует
собственную конфигурацию провайдера:

```shell
reviewmatic record-participants --draft <draft> --input participants.json \
  --ocr-provider openai --ocr-model claude-opus-4-6
```

Запись состава без критиков `engine: "ocr"` отклоняет флаги с адресной
ошибкой, поэтому случайная конфигурация никогда не срабатывает молча.

## Запуск критика

После записи контекстного пакета рантайм возвращает готовую задачу для каждого
критика. Задача модельного критика несёт шаблон квитанции и
`import_command`; задача OCR-критика несёт точную `run_command`:

```shell
reviewmatic record-ocr-critic --draft <draft> --participant ocr-critic
```

Для локального ревью та же команда указывает на снимок:

```shell
reviewmatic record-ocr-critic --bundle <snapshot> --participant ocr-critic
```

Один вызов выполняет весь механический проход критика:

1. Рендерит записанный контекстный пакет в Markdown-файл background под
   корнем артефактов.
2. Вызывает `ocr review --format json --audience agent` с таймаутом 300 секунд —
   по записанному диапазону base..head в управляемом review worktree для
   удалённого MR или в режиме workspace (staged, unstaged и untracked
   изменения) для локального ревью без ref.
3. Мапит каждый комментарий OCR в одну квитанцию: `severity`, `path` и
   `start_line`..`end_line` попадают в поля находки, `category` и
   `suggestion_code` питают текст исправления и риска, а квитанция хранит
   идентичность запуска OCR и метку `engine: "ocr"` с провайдером, моделью,
   терминальным состоянием и числом комментариев.
4. Импортирует квитанцию дословно стандартным путём `record-critic` и
   привязывает её к участнику, точно как квитанцию модельного критика.

Если OCR CLI отсутствует, падает или возвращает запуск без постоянной
идентичности сессии, команда завершается конкретной ошибкой, а черновик
остаётся неизменным; повторите команду после починки настройки OCR.

## Арбитраж и границы

Арбитр получает квитанции OCR вместе с модельными и выносит вердикт по каждой
находке OCR. Поскольку OCR даёт только находки, панель без модельных критиков
должна закрыть каждый вопрос, назначенный критикам, через
`question_verifications` в квитанции арбитра. Инкрементальное ревью сужает
OCR-критика до дельты `from_head..head`: квитанция связывается дайджестом
инкрементальной дельты, а `target_finding_ids` называет ровно те прошлые
находки, что отрендерены в background — те, чья прежняя позиция публикации
или патч пересекается с изменёнными путями. Локальные OCR-критики остаются
на полном диапазоне: локальная схема квитанции не имеет полей скоупа, поэтому
инкрементальные локальные панели запускают модельных критиков по дельте.
