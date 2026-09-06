# Общий interaction contract

Все workflows используют lifecycle `resolve -> prepare -> present -> confirm ->
apply -> report`. Пропускай только стадии, которые не применимы к операции:
read-only workflow завершает `prepare -> present -> report` без `confirm` и
`apply`; prompt-only workflow соблюдает тот же наблюдаемый протокол в диалоге и
не обязан добавлять runner.

## Question и Confirmation

**Question** задавай только до `prepare`, когда от человека зависит ещё не
принятое решение: target, scope, вариант результата или допустимый риск. Не
задавай вопрос о факте, который уже подтверждён evidence. Широкий GitLab target
(проект, список, поиск или фильтр) требует Question с точной границей до любого
listing или API-вызова; это не Confirmation.

**Confirmation** запрашивай только после `prepare` точной локальной или внешней
mutation. Создание private preview artifact на `prepare` не является mutation,
требующей Confirmation. Read-only collection, review и подготовка ручного плана
не требуют Confirmation и не меняют внешнее состояние.

## Present и apply

Human preview по умолчанию содержит только TLDR, scope, risks, checks, путь к
полному content-addressed write-once artifact и его SHA-256 digest. Полный draft
или diff в чат не выводи. Conflicts всегда показывай полностью, не скрывай и не
обрезай. Для подтверждаемой CLI mutation дополнительно покажи TTL и готовую
apply-команду с digest.

Executable apply принимает digest prepared preview. Он отклоняет отсутствующий,
изменённый, stale, просроченный или уже использованный plan до записи. После
успеха верни отдельный report с результатом и выполненными checks. JSON runners
возвращают compact summary, artifact/report path и SHA-256 digest; ошибки
возвращают JSON и ненулевой exit code.

## Границы

Не публикуй и не изменяй внешнее состояние в GitLab prepare/review workflows.
Не меняй user-owned configuration без Confirmation. После `report` остановись;
следующий workflow требует нового запроса.
