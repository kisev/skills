# Agent Skills

Этот репозиторий - публичный источник переносимых Agent Skills и будущего
необязательного npm package для интеграции с OpenCode.

## Установка skill

Установите canary skill напрямую из этого репозитория через `npx skills`:

```shell
npx skills add . --skill askme --agent codex --agent opencode --copy
```

Чтобы посмотреть доступные в checkout skills, выполните
`npx skills add . --list`.

## Границы

- `skills/` содержит переносимые самодостаточные skills, устанавливаемые через
  `npx skills`.
- `packages/opencode/` описывает границу будущего необязательного package для
  agents, commands и plugins OpenCode. Сейчас он не реализован.
- Пользовательского CLI нет. Python используется только в runners skills и
  maintainer scripts.
- После установки skill должен работать, не читая файлы за пределами своего
  каталога. Общие исходные материалы перед выпуском детерминированно
  копируются в каждый skill-потребитель.

Репозиторий распространяется по лицензии MIT. См. [LICENSE](LICENSE).

## Проверки сопровождающего

```shell
python3 scripts/sync_shared.py
python3 scripts/sync_shared.py --check
python3 -m unittest discover -s tests -v
npx --yes skills add . --list
uvx --from skills-ref agentskills validate skills/askme
```

Команда `npx skills` - интерфейс установки. Репозиторий не добавляет другой
установщик и не содержит скрытой зависимости от OpenCode.
