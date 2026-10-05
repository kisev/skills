# safe-fs

[English version](README.md)

`@kisev/safe-fs` — общие примитивы безопасной работы с файловой системой для
пакетов kisev: `writeAtomic` для приватной атомарной замены файлов с одной
ссылкой, `readRegular` для чтения только обычных файлов, `assertSafePath` для
обхода без симлинков и тип ошибки `LifecycleError`.

## Установка

```bash
# Registry version
npm view --prefer-online @kisev/safe-fs@latest version

# Install in this npm project
npm install @kisev/safe-fs

# Installed dependency
npm list @kisev/safe-fs --depth=0
```

Тег может сдвинуться между просмотром и установкой; `npm list` показывает
зависимость, реально установленную в этом проекте. У библиотеки нет CLI.

Каждая запись идёт через эксклюзивный временный файл с `fsync`, ограничением
прав и синхронизацией каталога; симлинки, файлы с несколькими ссылками и
каталоги-не-родители отклоняются.
