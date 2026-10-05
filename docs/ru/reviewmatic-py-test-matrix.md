# Матрица тестов Python-порта reviewmatic

[English version](../reviewmatic-py-test-matrix.md)

Авторитетный счёт TypeScript на этой ревизии — `node --test
--test-reporter=tap` по `apps/reviewmatic/test/*.test.mjs`: **201 тест, 201
проходит, 0 падений, 0 пропусков** (26 файлов; на три TUI-файла `tui-app`,
`tui-pty`, `tui-support` приходится 6 тестов). Бэкенд-выборка, которую
запускает сам `apps/reviewmatic` (`scripts/test.mjs`, все файлы кроме TUI), —
**195 тестов, 195 проходит**. Оба числа получены на ревизии, добавившей этот
файл, с собранным `dist/`.

## Карта модулей dist на Python-швы

| Модуль TypeScript (`dist/<name>.js`) | Python-шов |
| - | - |
| `contract.js` | `reviewmatic.portable.portable_gitlab.contract` (материализованный канон) |
| `state-artifacts.js` | `reviewmatic.portable.state_artifacts` (материализованный канон) |
| `mutation-process.js` | `reviewmatic.portable.mutation_process` (материализованный канон) |
| `review-semver.js` | `reviewmatic.portable.portable_gitlab.review_semver` (материализованный канон) |
| `label-assessment.js` | `reviewmatic.portable.portable_gitlab.label_assessment` (материализованный канон) |
| `context.js` | `reviewmatic.context` (возрождён из докового эталона) |
| `workflow.js` | `reviewmatic.workflow` (возрождён из докового эталона) |
| `publication.js` | `reviewmatic.publication` (переведён из исходника TypeScript) |
| `cli.js` | `reviewmatic.cli` (поверхность этапа 1; бизнес-диспетчеризация приходит вместе с каждым перенесённым модулем) |
| `local-review.js` | план: `reviewmatic.local_review` |
| `draft.js` | план: `reviewmatic.draft` |
| `context-package.js` | план: `reviewmatic.context_package` |
| `scope.js` | план: `reviewmatic.scope` |
| `fixes.js` | план: `reviewmatic.fixes` |
| `schema-issues.js` | план: `reviewmatic.schema_issues` |
| `worktree.js` | план: `reviewmatic.worktree` |
| `review-worktree.js` | план: `reviewmatic.review_worktree` |
| `version.js` | `reviewmatic.__version__` (метаданные пакета) |
| `tui/*` | вне объёма этапа 2 (этап 3 сохраняет интерфейс экспериментальным) |

## Матрица по файлам

| Файл тестов TypeScript | Тестов TS | Статус | Python-шов |
| - | - | - | - |
| `cli.test.mjs` | 4 | план (бизнес-диспетчеризация) | `tests/test_cli_contract.py` держит покрытие поверхности этапа 1 |
| `context-package.test.mjs` | 15 | план | `tests/test_context_package.py` |
| `context.test.mjs` | 6 | частично | `tests/test_context_report.py` несёт регрессии отчёта; регрессии сборки контекста приходят с портом context |
| `contract.test.mjs` | 38 | частично | `tests/test_contract_validators.py` (валидаторы, лейблы, предпросмотр, привязки critic/decision), `tests/test_golden_parity.py` (канонические дайджесты, вердикты артефактов), `tests/test_cli_contract.py` (capabilities); транспорт/сборка приходят с портом local-review |
| `draft-input.test.mjs` | 13 | план | `tests/test_draft_input.py` |
| `draft.test.mjs` | 6 | план | `tests/test_draft.py` |
| `glab-transport.test.mjs` | 1 | план | `tests/test_glab_transport.py` |
| `local-panel.test.mjs` | 1 | план | `tests/test_local_panel.py` |
| `local-review.test.mjs` | 26 | план | `tests/test_local_review.py` (предок `tests/test_local_review.py` из `320520a^` — база возрождения) |
| `mutation-process.test.mjs` | 6 | план | `tests/test_mutation_process.py` |
| `panel.test.mjs` | 4 | план | `tests/test_panel.py` |
| `publication.test.mjs` | 3 | частично | `tests/test_context_report.py::test_publication_make_command_keeps_plain_glab_commands` и `::test_structured_preview_accepts_manual_actions` |
| `repair.test.mjs` | 13 | план | `tests/test_repair.py` |
| `review-contract-regressions.test.mjs` | 15 | частично | `tests/test_contract_validators.py` несёт регрессии валидаторов канона |
| `review-semver.test.mjs` | 11 | покрыто выше | `tests/test_review_semver.py` (репозиторный набор) плюс golden-фикстуры `semver_*` |
| `review-worktree.test.mjs` | 17 | план | `tests/test_review_worktree.py` |
| `state-artifacts.test.mjs` | 11 | покрыто выше | `tests/test_state_artifacts.py` (репозиторный набор) плюс golden-фикстуры маркеров |
| `test-selection.test.mjs` | 1 | не применимо | бэкенд-выборка — забота раннера TypeScript; у pytest-набора нет TUI-разделения |
| `tui-app.test.mjs` | 3 | намеренно сокращено | этап 3 (TUI); на этапе 2 команда `plan` отвечает конвертом not-implemented этапа 1 |
| `tui-pty.test.mjs` | 1 | намеренно сокращено | этап 3 (TUI) |
| `tui-support.test.mjs` | 2 | намеренно сокращено | этап 3 (TUI) |
| `workflow.test.mjs` | 2 | частично | возрождённый `reviewmatic.workflow` проверяется через `tests/test_context_report.py`; регрессия диспетчера приходит с проводкой CLI |
| `worktree.test.mjs` | 2 | план | `tests/test_worktree.py` |

Строки «план» — оставшаяся дельта этапа 2; указанные файлы-швы — согласованные
места приземления, чтобы ни один тест TypeScript не терялся молча. Матрица
обновляется тем же изменением, которое приносит очередную строку.

## Fake glab

Набор TypeScript гоняет `helpers/review-fixture.mjs`, который кладёт на `PATH`
подменный `glab` (скрипт Node) и записывает каждый запрос. Python-порт
переписывает хелпер на Python с тем же контрактом записи запросов; паритет
несут перенесённые тесты журнала запросов. Это держит тесты пакета на одной
стандартной библиотеке вместо зависимости от рантайма Node.
