# Portable Skills Distribution

[Русский](README.ru.md)

This private manifest sets the version of the portable distribution built by CI
and deployed to GitHub Pages. `task distribution:build` produces the standard
well-known discovery index, integrity metadata, and one self-contained archive
per public skill. Skills carry no version; release identity belongs to the
distribution metadata and each archive's content digest. This directory is not
published to npm.
