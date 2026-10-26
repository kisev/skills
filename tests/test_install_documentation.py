"""Keep installation examples transparent about the source they install from."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAIRS = (
    ("README.md", "README.ru.md"),
    ("apps/memomatic/README.md", "apps/memomatic/README.ru.md"),
    ("apps/taskmatic/README.md", "apps/taskmatic/README.ru.md"),
    ("packages/safe-fs/README.md", "packages/safe-fs/README.ru.md"),
    ("docs/how-to/install-skills.md", "docs/ru/how-to/install-skills.md"),
    ("docs/how-to/memomatic.md", "docs/ru/how-to/memomatic.md"),
    ("docs/how-to/portable-skills.md", "docs/ru/how-to/portable-skills.md"),
    ("docs/how-to/taskmatic.md", "docs/ru/how-to/taskmatic.md"),
    ("docs/tutorials/getting-started.md", "docs/ru/tutorials/getting-started.md"),
    ("docs/verification.md", "docs/ru/verification.md"),
)


def installation_blocks(path: str) -> list[str]:
    return [
        block
        for block in re.findall(r"```(?:shell|bash)\n(.*?)```", (ROOT / path).read_text(), re.S)
        if "npm install" in block or "skills@latest add" in block
    ]


@pytest.mark.parametrize(("english", "russian"), PAIRS)
def test_installation_examples_preview_run_and_verify_in_both_locales(
    english: str,
    russian: str,
) -> None:
    blocks = installation_blocks(english)
    assert blocks == installation_blocks(russian), english
    for block in blocks:
        # A checkout build precedes every install from a checkout; the skills
        # CLI channel names the Pages source it reads.
        if "npm install --global ./apps/" in block:
            assert "task generate" in block
            assert "npm view" not in block
        if "skills@latest add" in block:
            assert "https://kisev.github.io/skills" in block
            assert "skills@dev" not in block
        # Every install in this repository is non-interactive only through an
        # explicit flag; plain commands preview instead of writing.
        assert not re.search(r"^npm install --global @kisev/", block, re.M)


def test_complete_setup_checks_every_installed_application() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "uvx skillmate install --yes" in text
    assert "skills@latest add https://kisev.github.io/skills --global" in text
    assert "--from-checkout /path/to/skills --yes" in text
    assert "uvx --from" in text
    assert "#subdirectory=apps/reviewmatic" in text
    assert "npm view --prefer-online @kisev/" not in text


def test_reviewmatic_git_install_is_mirrored_and_documents_ref_and_cache() -> None:
    english = (ROOT / "apps/reviewmatic/README.md").read_text(encoding="utf-8")
    russian = (ROOT / "apps/reviewmatic/README.ru.md").read_text(encoding="utf-8")
    command = (
        'uvx --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}'
        '#subdirectory=apps/reviewmatic" reviewmatic'
    )
    for document, stable_ref, dev_ref in (
        (english, "exact release tag", "moving `dev` branch"),
        (russian, "точный тег выпуска", "ветку `dev`"),
    ):
        normalized = " ".join(document.split())
        assert command in normalized
        assert stable_ref in normalized
        assert dev_ref in normalized
        assert "--refresh-package reviewmatic" in normalized
        assert "uv cache clean" in normalized
        assert "uv tool install" in normalized
        assert "PyPI" in normalized
