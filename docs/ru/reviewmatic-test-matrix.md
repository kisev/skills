# Baseline тестов reviewmatic и матрица переноса

[English version](../reviewmatic-test-matrix.md)

Сохранённый TypeScript-baseline измерен до удаления на ревизии исходников
`3e409c217e94d643f77eb543caab9a2ed4b7288d`. При собранном пакете команда
`node --test --test-reporter=tap` по `apps/reviewmatic/test/*.test.mjs` дала
**201 тест, 201 проходит, 0 падений, 0 пропусков** (26 файлов). Backend-набор
содержал **195 тестов, 195 проходит**; оставшиеся 6 приходились на три TUI-файла
(`tui-app`, `tui-pty`, `tui-support`). Python-baseline проверяют
`task reviewmatic:check` и `task test:python`; TypeScript-раннера и генератора
в репозитории больше нет.

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
| `cli.js` | `reviewmatic.cli` (команды ревью и локального WIP; TUI-команда `plan` удалена) |
| `local-review.js` | `reviewmatic.local_review` (переведён из исходника TypeScript) |
| `draft.js` | `reviewmatic.draft` (переведён из исходника TypeScript; полная стейт-машина) |
| `context-package.js` | `reviewmatic.context_package` (переведён из исходника TypeScript) |
| `scope.js` | `reviewmatic.scope` (переведён из исходника TypeScript) |
| `fixes.js` | `reviewmatic.fixes` (переведён из исходника TypeScript) |
| `schema-issues.js` | `reviewmatic.schema_issues` (переведён; канон регистрирует `schema_valid` как оракул при импорте пакета) |
| `worktree.js` | `reviewmatic.worktree` (переведён из исходника TypeScript) |
| `review-worktree.js` | `reviewmatic.review_worktree` (переведён из исходника TypeScript) |
| `version.js` | `reviewmatic.__version__` (метаданные пакета) |
| `tui/*` | удалён вместе с TypeScript-приложением; замены интерфейсу нет |

## Матрица по файлам

| Файл тестов TypeScript | Тестов TS | Статус | Python-шов |
| - | - | - | - |
| `cli.test.mjs` | 4 | перенесено | `tests/test_cli_contract.py` (поверхность version/help/capabilities/publication/marker-run и утверждения бизнес-диспетчеризации этапа 2) |
| `context-package.test.mjs` | 15 | перенесено | `tests/test_context_package.py` (дайджесты, версионирование, вывод из обращения, привязки ответов/проверок, валидация MR) и `tests/test_context_package_records.py` (все пятнадцать сквозных сценариев записи через fake glab; адресные диагностики схемы дают локатор схемы канона, регистрируемый при импорте пакета) |
| `context.test.mjs` | 6 | перенесено | `tests/test_context_report.py` (регрессии отчёта), `tests/test_review_happy_path.py` (счастливый путь стейт-машины через fake glab), `tests/test_context_scenarios.py` (действие раннера, переходы прогресса, строковые публикации, гейтинг вердикта, атомарная публикация состояния и хвост неизменённого второго прогона) |
| `contract.test.mjs` | 38 | перенесено | `tests/test_contract_scenarios.py` (все тридцать восемь сценариев со встроенными Python-фейками glab через `tests/helpers/contract_support.py`), `tests/test_contract_validators.py`, `tests/test_golden_parity.py`, `tests/test_cli_contract.py`; парсеры `glab_text`, трассы и semver возвращают в Python кортежи |
| `draft-input.test.mjs` | 13 | перенесено | `tests/test_draft_input_scenarios.py` (все тринадцать сценариев; CLI-сценарии запускают `python -m reviewmatic`; TUI-хелперы плана сведены к артефакту плана и действиям его предпросмотра) и `tests/test_draft_lifecycle.py` |
| `draft.test.mjs` | 6 | перенесено | `tests/test_draft_scenarios.py` (все шесть сценариев; утверждения TUI `amendBody` и `itemText` сведены к эквивалентам уровня плана) и `tests/test_draft_lifecycle.py` |
| `glab-transport.test.mjs` | 1 | перенесено | `tests/test_glab_transport.py` (закреплённый настоящий glab против локального сервера; без пропусков) |
| `local-panel.test.mjs` | 1 | перенесено | `tests/test_local_panel.py` |
| `local-review.test.mjs` | 26 | перенесено | `tests/test_local_review_cycle.py` (цикл исправлений, вердикт), `tests/test_local_review_preparation.py` (восемнадцать сценариев подготовки, границ и CLI), `tests/test_local_review_scenarios.py` (шесть сценариев привязки пакета; `finalize-local` отклоняет устаревший ответ для локальных снимков после исправления `evidence_kind` в каноне) |
| `mutation-process.test.mjs` | 6 | перенесено | `tests/test_mutation_process.py` |
| `panel.test.mjs` | 4 | перенесено | `tests/test_panel.py` (TUI-хелпер `loadPlan` заменён чтением артефакта плана через указатель прогресса) |
| `publication.test.mjs` | 3 | перенесено / UI удалён | `tests/test_context_report.py` и `tests/test_publication_scenarios.py` проверяют команды runbook и head-guard на fake glab; отмена через `AbortSignal` относилась только к удалённому TUI |
| `repair.test.mjs` | 13 | перенесено | `tests/test_fixes_and_diagnostics.py` (диагностика схемы, синтез предложений) и `tests/test_repair.py` (сквозные сценарии ремонта, refresh и дрейфа CI; утверждение TUI `planItems` сведено к действиям предпросмотра публикации, из которых оно выводится) |
| `review-contract-regressions.test.mjs` | 15 | перенесено | `tests/test_review_contract_regressions.py` (все одиннадцать определений); утверждения про routing-ответ используют поле черновика и созданные блоки runbook без TUI-адаптера |
| `review-semver.test.mjs` | 11 | покрыто выше | `tests/test_review_semver.py` (репозиторный набор) плюс golden-фикстуры `semver_*` |
| `review-worktree.test.mjs` | 17 | перенесено | `tests/test_review_worktree.py` (правила уровня модуля) и `tests/test_review_worktree_scenarios.py` (все семнадцать сквозных сценариев с настоящей параллельностью процессов) |
| `state-artifacts.test.mjs` | 11 | покрыто выше | `tests/test_state_artifacts.py` (репозиторный набор) плюс golden-фикстуры маркеров |
| `test-selection.test.mjs` | 1 | не применимо | бэкенд-выборка относится к раннеру TypeScript; у pytest-набора нет TUI-разделения |
| `tui-app.test.mjs` | 3 | удалено вместе с интерфейсом | навигация Ink и отправка отсутствуют в Python-рантайме |
| `tui-pty.test.mjs` | 1 | удалено вместе с интерфейсом | нет терминального интерфейса и PTY-команды |
| `tui-support.test.mjs` | 2 | удалено вместе с интерфейсом | UI-хелперы не относятся к runtime-поведению |
| `workflow.test.mjs` | 2 | перенесено | `tests/test_workflow_dispatch.py` |
| `worktree.test.mjs` | 2 | перенесено | `tests/test_worktree.py` (оба сценария плюс защищённое удаление, которое набор TypeScript не покрывает) |

Для каждого поведенческого backend-теста есть Python-шов. Проверка отбора
файлов в TypeScript-раннере не была поведением приложения и удалена вместе с
раннером. Шесть TUI-тестов удалены вместе с интерфейсом, а не оставлены как
пропуски. Golden-фикстуры хранят дайджесты,
вердикты TypeScript и переходы стейт-машины (`draft_gaps`,
`superseded_results`, `analysis_fingerprint`). Python заново вычисляет и
утверждает все ожидания, но не генерирует ожидаемые значения из самого себя.

## Fake glab

Набор TypeScript гоняет `helpers/review-fixture.mjs`, который кладёт на `PATH`
подменный `glab` (скрипт Node) и записывает каждый запрос. Python-порт
переписывает хелпер на Python с тем же контрактом записи запросов; паритет
несут перенесённые тесты журнала запросов. Это держит тесты пакета на одной
стандартной библиотеке вместо зависимости от рантайма Node.

## Слои приёмки скилла

У скилла code-review два слоя приёмки поверх обычного набора тестов
(решение 64: репозиторий сам прогоняет полный цикл ревью на тестовом
фикстуре, поэтому закоммитить сломанный цикл детерминированно невозможно, а
агентный излом видно немедленно).

Детерминированный слой сидит внутри существующих фулл-цикл тестов. Тест
run-цикла сеет `closes_issues` и принимает завершённый прогон по артефактам и
журналу запросов фикстуры: остановка опроса отдаёт агенту дословный текст
опроса плюс правила заземления в каталоге агентов; связанные issues попадают
в контекст ревью с происхождением `author_text`; авторские метки Conventional
Comments в скелетах ответов доживают до тела публикации; весь цикл ходит
через единственный подменный glab из
`tests/helpers/review_fixture.py`. Эти ассерты едут в `task check` обычным
порядком pytest-набора.

Агентный слой — задача `task test:integration:skills:acceptance`
(`tests/integration/gitlab/scripts/skill_acceptance.py`). Она собирает
фикстуру с подменным glab, предпосеивает каталог агентов хоста, пинит
рантайм reviewmatic на текущую ревизию чекаута и просит одну реальную сессию
`opencode run --standalone` провести полный цикл ревью из временного
чекаута. Проверка машинная — по артефактам и событиям stdout-JSONL хоста:
опрос предъявлен дословно, вопрос состава задан родным интерактивным
вопрос-инструментом хоста с минимальным набором опций (решение 71; в
неинтерактивном прогоне вызов отменяется и действует предзаданный ответ),
чек критика импортирован, проза авторская,
дисциплина чтения соблюдена (ноль чтений `references/` вне файлов своей
стадии), ни одной публикации против подменного glab, плюс независимая
ревалидация `reviewmatic report-review`. Разбор базы сессий хоста не
используется никогда.

Честные границы агентного слоя: GitLab — фикстура с подменным glab, а не
настоящий сервер, публикации не исполняются, и поведение модели
недетерминировано — зелёный вердикт значит, что одна реальная модель прошла
цикл и все машинные проверки, с ретраем только для транспортных сбоев.
Независимость панели критиков сохраняется: приёмка требует запустить критика
отдельной субагентской сессией (инструмент subagent в opencode её даёт) и
заваливает чек, подписанный идентичностью primary-сессии.
Задача работает с дефолтами (модель `zai-coding-plan/glm-5.3-flash`,
таймаут 90 минут и щедрые бюджеты токенов/стоимости) и полностью настраивается
через переменные `EVAL_MODEL`, `EVAL_TIMEOUT`, `EVAL_MAX_TOKENS` и
`EVAL_MAX_COST`; учётные данные провайдера всегда явные. Она
намеренно вне `task check`, `check:core`, гейта Lefthook pre-push, CI-матрицы
и `gate-registry.json` (того же класса, что `eval:live`).

Агентный слой запускайте на каждой волне, трогающей тексты code-review, и
перед релизом. Детерминированный слой работает при любом изменении в
репозитории — это обычный тест.

## Зонтик приёмки

`task acceptance` (`tests/integration/acceptance.py`) — единый пускатель всех
живых семейств: он ведёт агентный слой выше, живые прогоны GitLab и
Mattermost и по одному минимальному поведенческому пробу на каждый непокрытый
скилл (`tests/integration/acceptance_probes.py`). Каждый проб ставит в
изолированный sandbox хоста только свой скилл, подкладывает маленькие
fixture-файлы и машинно проверяет артефакт; скиллы, для которых
синтетический fixture не имеет смысла, пропускаются с причиной в отчёте.
Каждый прогон пишет `result.json` и `summary.md` в
`.build/acceptance/<timestamp>/` и печатает построчный прогресс (скилл,
семейство, этап, модель, секунды). Модель по умолчанию — дешёвая
flash-класса; любую `EVAL_*` можно переопределить, недешёвая модель требует
явного `--yes` или `ACCEPT_EXPENSIVE=1`. Wall-clock время полного цикла
code-review — отдельный критерий приёмки: 30 минут на fixture выше, тайминги
по этапам, превышение — красный вердикт. Как запускать, где отчёты и как
передать отчёт master-сессии — [в how-to](../how-to/skill-acceptance.md).
Зонтик остаётся вне `task check`, `check:core`, Lefthook, CI и реестра
гейтов.
