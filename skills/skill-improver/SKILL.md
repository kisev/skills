---
name: skill-improver
description: >-
  Итеративно проверить и улучшить один Agent Skill через цикл check, исправление
  и recheck. Использовать для frontmatter, ресурсов, progressive disclosure и
  объявленных scripts, а не для разовой стилистической правки.
license: MIT
compatibility: Требует Python 3.12+ только со стандартной библиотекой.
metadata:
  author: "Kirill Sevriugin"
  version: "1.1.0"
---

# Итеративное улучшение skill

## Граница target

Навык принимает ровно один существующий каталог с `SKILL.md` или путь к самому
`SKILL.md`. Несколько skills проверяй отдельными запусками. Не ищи skills в
глобальных каталогах и не выбирай target по догадке: при отсутствии пути задай
один уточняющий вопрос.

Из каталога skill запусти read-only checker:

```shell
python3 -I -S -B scripts/skill_improver.py check --path <SKILL_DIR>
```

Runner выводит один JSON. Exit code `0` означает отсутствие critical и major
замечаний, `1` - наличие critical или major, `2` - ошибка использования. У
`--capabilities` нет побочных действий.

## Цикл

1. Выполни `check` для одного target и прочитай JSON.
2. Перед первой записью покажи список critical и major замечаний, точные пути и
   planned diff; получи подтверждение.
3. Исправь причины critical и major замечаний, не переписывая skill ради стиля.
4. Каждый minor оцени отдельно и пропусти ложное срабатывание с краткой причиной.
5. Повтори `check` до exit code `0`. После правок запусти доступные проверки
   target skill.
6. Только при чистом результате заверши отдельной строкой
   `<skill-improvement-complete>`. До него перечисли сознательно пропущенные
   minor с причиной.

## Severity checker-а

- `critical`: отсутствующий или невалидный frontmatter, недопустимое имя,
  несовпадение имени и каталога, отсутствующее description, unsafe/broken resource
  path или объявленный отсутствующий script.
- `major`: слишком длинное description, неподдерживаемое поле frontmatter,
  script без работающего `--help` или `SKILL.md` длиннее 500 строк без
  `references/` для progressive disclosure.
- `minor`: незакрытый TODO или FIXME.

Checker проверяет Agent Skills, а не commands, plugins, agents или инструменты
конкретного host.
