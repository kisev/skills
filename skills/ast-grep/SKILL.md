---
name: ast-grep
description: >-
  Выполнять структурный поиск или подтверждённый rewrite через ast-grep, когда
  синтаксическое дерево важнее текстового совпадения. Использовать для точных
  AST-преобразований с preview и защитой от drift.
license: MIT
compatibility: Требует установленный CLI ast-grep и Python 3.12+ только со стандартной библиотекой.
metadata:
  author: "Kirill Sevriugin"
  version: "1.0.0"
---

# Структурный поиск и rewrite

Используй AST search вместо текстового поиска, когда важны границы узлов и
metavariables. Для простого текста текстовый поиск быстрее и понятнее. Pattern
использует синтаксис ast-grep: `$NAME` - один узел, `$$$NAME` -
последовательность узлов, а повторяющиеся metavariables должны совпасть.

Внешний CLI не устанавливается этим skill. `python3 -I -S -B
scripts/ast_grep.py --capabilities` сообщает его фактическую доступность. Если
binary отсутствует, runner возвращает JSON `escalate`. Не выполняй автоустановку.

## Search

Из каталога skill выполни только read-only поиск:

```shell
python3 -I -S -B scripts/ast_grep.py search \
  --pattern 'const $A = $B' --lang javascript PATH
```

Покажи structured matches: file, range, matched text и metavariables. Не
изменяй файлы и не предлагай apply, если пользователь запросил только поиск.

## Rewrite

Цели rewrite должны быть обычными non-symlink файлами внутри существующего
non-symlink workspace. Сначала всегда создай preview:

```shell
python3 -I -S -B scripts/ast_grep.py rewrite \
  --pattern 'const $A = $B' --rewrite 'let $A = $B' \
  --lang javascript --workspace PATH PATH
```

Покажи затронутые файлы, число matches, diff и `confirmation` digest. При нулевом
match сообщи no-op без подтверждения. До явного подтверждения пользователя не
добавляй `--apply`. После подтверждения повтори ровно тот же вызов с
`--apply --confirm <DIGEST>`. Runner повторно строит preview, отклоняет другой
digest, stale target, traversal и symlink без записи; подготовка всех файлов
заканчивается до первой замены, а ошибка замены откатывает уже заменённые файлы.
