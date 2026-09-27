# Добавление и переименование npm-пакета рабочей области

[English](../../how-to/npm-package-lifecycle.md)

Используйте этот рецепт, чтобы добавить, переименовать или удалить npm-пакет
рабочей области. Каждое имя пакета участвует в полном графе публикации: wiring
рабочей области, граф задач, dev- и release-упаковка, порядок публикации,
smoke-тесты и привязки trusted publisher в npm по каждому имени. Имя, не
покрытое хотя бы одной поверхностью, ломает CI или Publish.

Контрактный тест `test_every_workspace_package_is_wired_into_the_publication_graph`
в `tests/test_tooling_contracts.py` падает со ссылкой на эту страницу, как
только список рабочих областей и граф публикации расходятся.

## Перепайка графа репозитория

Обновите каждую поверхность для нового имени в порядке зависимостей
(`@kisev/safe-fs` раньше `@kisev/memomatic` и `@kisev/agentomatic`):

| Поверхность | Что обновить |
| - | - |
| `package.json` (корень) | Точный список `workspaces`; закреплён контрактными тестами |
| `package-lock.json` | Перегенерировать через `npm install` |
| `taskfile.yml` | `package:build` собирает зависимости раньше потребителей; `typecheck:typescript` сохраняет `deps: [package:build]` |
| `scripts/build_dev_artifacts.py` | Кортеж `members` в порядке зависимостей; пиннинг dev-зависимостей выводится автоматически |
| `scripts/build_release_artifacts.py` | `PACKAGE_MEMBERS` в том же порядке |
| `scripts/publish_npm_release.py` | `NPM_PUBLISH_ORDER` и ожидания `registry_smoke` |
| `packages/agentomatic/test/smoke.mjs` | Переменные окружения для tarball'ов и список установки |
| `tests/test_tooling_contracts.py` | Закрепление workspaces и порядок сборки |
| `tests/test_release_contract.py` | Записи участников манифеста |

Зависимости между пакетами рабочей области задаются диапазонами `^` в
исходных `package.json`; упаковка dev-тарball'ов переписывает их в точные
dev-версии, поэтому чистые чекауты и установки из реестра никогда не уходят
в публичный npm за внутренними зависимостями.

## Контракт CLI

Каждый пакет с полем `bin` обязан поддерживать:

- `--version`: напечатать ровно версию из установленного `package.json`, не
  создавать каталогов состояния и не трогать XDG-пути.
- `--help`: код возврата 0.

Контракт проверяется дважды: `smoke.mjs` в локальном гейте `task check` и
`registry_smoke` после публикации. CLI, не отвечающий на `--version`, роняет
Publish через несколько минут после успешной загрузки.

## Bootstrap нового имени пакета в npm

Trusted publishing привязывается к существующему имени пакета в его
настройках; OIDC-воркфлоу не может создать новое имя, и предварительная
регистрация недоступна. Каждое новое имя один раз бутстрапится из терминала:

```shell
npm --version          # npm 11.15.0 or newer
npm logout
npm login --auth-type=web

# Download the exact validated tarballs from the producing Publish run
gh run download <run-id> -n npm-dev-<run-id>-1 -D .build/release

# Publish in dependency order, then bind the trusted publisher
npm publish .build/release/safe-fs.tgz   --tag dev --access public
npm publish .build/release/memomatic.tgz --tag dev --access public
npm publish .build/release/package.tgz   --tag dev --access public

# npm never allows deleting `latest`; retarget it to a published version
npm dist-tag add @kisev/safe-fs@<newest-dev-version> latest    # no stable release yet
npm dist-tag add @kisev/memomatic@<newest-dev-version> latest  # no stable release yet
npm dist-tag add @kisev/agentomatic@<stable-version> latest    # name with a stable release

npm trust github @kisev/safe-fs    --repo kisev/skills --file publish.yml --allow-publish --yes
npm trust github @kisev/memomatic --repo kisev/skills --file publish.yml --allow-publish --yes
npm trust github @kisev/agentomatic --repo kisev/skills --file publish.yml --allow-publish --yes
```

Первый `npm trust` требует 2FA; браузер предложит пропуск на пять минут для
оставшихся имён. Следующий пуш в `dev` публикуется уже через OIDC.

Завершите бутстрап проверкой, что ни один тег `latest` не ссылается на
prerelease:

```shell
npm dist-tag ls @kisev/agentomatic
npm dist-tag ls @kisev/safe-fs
npm dist-tag ls @kisev/memomatic
```

Ловушки:

- Версии, изданные из локального терминала, не несут provenance-аттестации.
  Не перезапускайте Publish-прогон, покрывающий локально изданные версии:
  проверка provenance упадёт по замыслу. Пусть следующий пуш их перекроет.
- npm назначает dist-tag `latest` на первую изданную dev-версию нового имени,
  а локальная публикация существующего имени сдвигает `latest`, когда изданная
  dev-версия по semver выше текущего `latest`.
- npm не позволяет удалять `latest` (registry отклоняет
  `npm dist-tag rm <name> latest` с ошибкой 400; см. npm/cli#8490). Пока у
  имени нет стабильного релиза, держите `latest` перенаправленным на новейшую
  dev-версию; когда стабильный релиз появится, гейт публикации упадёт, если
  `latest` всё ещё ссылается на prerelease.
- Совершенно новые имена распространяются медленно: отрицательное кэширование
  CDN способно съесть общий десятиминутный бюджет ожиданий на проверках
  metadata и tarball. Когда версии начнут отвечать 200, перезапустите только
  упавшие джобы с сохранёнными артефактами: `gh run rerun <run-id> --failed`.
- Dev-версии содержат 12-символьную короткую ревизию (`…dev.48.gf6e4f0e086aa`).
  Запрашивайте точечные endpoint'ы версий и используйте
  `npm view --prefer-online`, чтобы обойти закэшированные отрицательные ответы.

## Переименование существующего пакета

Переименование — это добавление плюс вывод старого имени из оборота:

1. Bootstrap нового имени, как описано выше.
2. Перепаять граф репозитория и мигрировать состояние рантайма и ссылки
   установщика тем же изменением.
3. Депрекировать старое имя; никогда не снимайте с публикации и не двигайте
   вышедшие версии и теги:

```shell
npm deprecate @kisev/old-name@* "Renamed to @kisev/new-name"
```
