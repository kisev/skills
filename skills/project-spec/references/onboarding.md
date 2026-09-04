# Подключение существующего проекта

Перед вопросами исследуй доступные repository evidence: инструкции, README и
документацию, ADR/RFC, исходный код, тесты, схемы, configuration, CLI/API,
dependencies, CI, deployment и integrations. Используй дополнительные исследования
только при необходимости; результаты держи в контексте, не в repository.

## Классификация evidence

- Классифицируй каждый отдельный claim, а не source file, subsystem или проект
  целиком. Один и тот же evidence может подтверждать implementation fact, но не
  intent человека или compatibility guarantee.
- `KNOWN`: конкретный claim однозначно подтверждён. Не спрашивай пользователя.
- `AMBIGUOUS`: evidence допускает несколько трактовок. Покажи варианты и спроси
  пользователя.
- `UNKNOWN`: repository не позволяет определить intent. Спроси пользователя.
- `CONFLICT`: sources противоречат друг другу. Покажи точные paths и различия,
  затем спроси, что считать нормативным.

Например, tests и source могут сделать claim "CLI принимает `--timeout`" `KNOWN`,
но claim "`--timeout` - поддерживаемый публичный контракт" остаётся `UNKNOWN`, если
это не подтверждено contract evidence или человеком.

Не реконструируй historical features, milestones, phases или первоначальный
roadmap. Описывай текущее устройство и договорённости, которые человек выбирает как
нормативные. Всегда различай "код сейчас так делает" и "это поддерживаемый
контракт".

Результат onboarding - только полный canonical `specs/` и ADR, если они
действительно нужны. Не создавай `research/`, `analysis/`, `planning/`, `mapping/`,
`state/` или отчёт об исследовании.
