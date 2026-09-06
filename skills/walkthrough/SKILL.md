---
name: walkthrough
description: >-
  Построить read-only экскурсию по большому Git diff: сгруппировать файлы,
  определить порядок чтения и связи между изменениями перед анализом. Использовать
  для current checkout, Git range или готового diff-file, но не для review verdict.
license: MIT
compatibility: Требует Git и Python 3.12+ только со стандартной библиотекой.
metadata:
  author: "Kirill Sevriugin"
  version: "1.1.1"
---

# Экскурсия по diff

Навык только читает checkout и не является ревью. Не меняй файлы, не выноси
verdict и не предлагай approve. Для оценки качества после экскурсии используй
отдельный workflow ревью.

## Runner

Из каталога skill запусти:

```shell
python3 -I -S -B scripts/walkthrough.py \
  --repo-root <REPO_ROOT> [--range <BASE..HEAD> | --diff-file <DIFF_FILE>] \
  [--chunk-size 8] [--chunk-index <INDEX>]
```

Без `--range` и `--diff-file` runner включает staged, unstaged и untracked
изменения относительно `HEAD`. Для range используй точный Git range. Для
готового diff-file передай уже полученный артефакт и не собирай другой diff.
`--capabilities` только читает доступность Git.

JSON runner-а является evidence: не пересчитывай статистику и связи вручную. При
нескольких chunks сначала прочитай `chunk_manifest`, затем последовательно
запрашивай каждый `--chunk-index`. Частичный результат имеет
`coverage.complete=false` и `uncovered_files`; явно покажи непокрытую часть и не
называй такой chunk полным diff.

## Рассказ по результату

Выдай нумерованные шаги в порядке `contracts -> logic -> tests -> configs`.
Каждый изменённый файл должен входить ровно в один шаг. Для каждого шага укажи
файлы, намерение по diff, что прочитать дальше и точные связи из
`relationships`. Отдельно покажи `attention` с файлами миграций, permissions и
удалений. Заверши явной границей: это карта чтения, а не оценка качества
изменений.
