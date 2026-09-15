# Дистрибуция portable skills

[English](README.md)

Этот private manifest задаёт версию portable distribution, которую CI собирает
и развёртывает на GitHub Pages. `task distribution:build` создаёт standard
well-known discovery index, integrity metadata и отдельный self-contained
archive для каждого public skill. Skills не содержат version; release identity
задают distribution metadata и content digest каждого archive. Этот каталог не
публикуется в npm.
