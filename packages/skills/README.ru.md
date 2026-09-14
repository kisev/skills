# Дистрибуция portable skills

[English](README.md) | [Русский](README.ru.md)

Этот private manifest задаёт версию portable distribution, которую CI собирает
и развёртывает на GitHub Pages. `task distribution:build` создаёт standard
well-known discovery index, integrity metadata и отдельный self-contained
archive для каждого public skill. Этот каталог не публикуется в npm.
