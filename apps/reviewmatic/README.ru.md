# reviewmatic

[English version](README.md)

`@kisev/reviewmatic` — исполняемый рантайм скилла `code-review`: полная цепочка
ревью (сбор доказательств GitLab, машина состояний ревью, иммутабельные планы,
охраняемая публикация) плюс интерактивный терминальный разбор готового плана
ревью.

## Установка

```bash
npm install --global @kisev/reviewmatic
```

Нужны Node.js 22.13+ и аутентифицированный для вашего GitLab CLI `glab`.
Состояние ревью хранится в `$XDG_STATE_HOME/agent-skills/code-review/` — там же,
куда пишут команды ревью.

## Цепочка ревью

Агент ведёт ревью теми же командами, на которые ссылается скилл:

```bash
reviewmatic prepare --url <mr-url> --repo-root <checkout> --review-mode normal --locale ru
reviewmatic context --evidence <path> --repo-root <checkout>
reviewmatic template-review --artifact-root <root> --kind critic
reviewmatic record-artifact --kind critic_receipt --evidence <path> --input <path>
reviewmatic finalize --artifact-root <root>
reviewmatic finalize-review --evidence <path> --report <path> --mode normal \
  --finalize-report <path> --context <path>
reviewmatic scaffold-review --evidence <path> --context <path> --decision <path> --content <path>
reviewmatic report-review --artifact-root <root>
```

Локальные ревью незакоммиченного используют `prepare-local` и `finalize-local`;
`status`, `next` и `assess-mode` показывают прогресс. Каждая команда печатает
компактный JSON и никогда не меняет GitLab или чекаут.

## Интерактивный разбор плана

После ревью агент печатает краткий саммари и одну команду:

```bash
reviewmatic plan --artifact-root <root>
```

Запустите её вручную в терминале. По каждому существующему треду видны
замечание, черновик ответа и явный выбор: отправить, отправить и закрыть либо
пропустить. Клавиша `e` открывает черновик в `$EDITOR`; перед отправкой план
пересобирается под отредактированное тело. Новые треды, рекомендуемые issues и
лейблы проходят тот же разбор. Саджесты и git-патчи дополнительно предлагают
локальное применение: reviewmatic создаёт отдельный git worktree на точном
reviewed head, показывает diff, а коммит и пуш запрашивает двумя отдельными
подтверждениями.

Каждая отправка идёт через охраняемый контракт публикации
(`reviewmatic publication apply/inspect/retry`): действия привязаны к
пользователю GitLab, refs MR, беседе и digest'ам тел; квитанции делают повторы
идемпотентными; неопределённый исход блокирует только своё действие и предлагает
сначала read-only инспекцию.

## Реестр worktree

Созданные worktree записываются в
`$XDG_STATE_HOME/agent-skills/reviewmatic/worktrees.json`. Ничего не удаляется
автоматически; `reviewmatic worktree list` печатает реестр с состоянием коммита
и пуша по каждому worktree.

## Контракт совместимости

Digest'ы и артефакты остаются байт-совместимыми с документированными контрактами
артефактов v2; canonical JSON сверяется с Python-референсом в тестах. Пакет не
создаёт состояния на `--help` и `--version`.
