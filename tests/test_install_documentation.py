"""Keep installation examples transparent about registry and local versions."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAIRS = (
    ("README.md", "README.ru.md"),
    ("apps/memomatic/README.md", "apps/memomatic/README.ru.md"),
    ("apps/reviewmatic/README.md", "apps/reviewmatic/README.ru.md"),
    ("apps/taskmatic/README.md", "apps/taskmatic/README.ru.md"),
    ("packages/agentomatic/README.md", "packages/agentomatic/README.ru.md"),
    ("packages/safe-fs/README.md", "packages/safe-fs/README.ru.md"),
    ("docs/how-to/memomatic.md", "docs/ru/how-to/memomatic.md"),
    ("docs/how-to/opencode-integration.md", "docs/ru/how-to/opencode-integration.md"),
    ("docs/how-to/portable-skills.md", "docs/ru/how-to/portable-skills.md"),
    ("docs/how-to/taskmatic.md", "docs/ru/how-to/taskmatic.md"),
    ("docs/tutorials/getting-started.md", "docs/ru/tutorials/getting-started.md"),
    ("docs/verification.md", "docs/ru/verification.md"),
)


def installation_blocks(path: str) -> list[str]:
    return [
        block
        for block in re.findall(r"```(?:shell|bash)\n(.*?)```", (ROOT / path).read_text(), re.S)
        if "npm view --prefer-online" in block
    ]


@pytest.mark.parametrize(("english", "russian"), PAIRS)
def test_installation_examples_preview_run_and_verify_in_both_locales(
    english: str,
    russian: str,
) -> None:
    blocks = installation_blocks(english)
    assert blocks, english
    assert blocks == installation_blocks(russian)
    for block in blocks:
        stages = re.split(r"\n\n(?=#)", block.strip())
        assert len(stages) == 3, (english, block)
        preview, install, verify = stages
        assert "npm view --prefer-online" in preview
        assert re.search(r"^(?:npm install|npx .* (?:add|install)) ", install, re.M)
        assert "npm list " in verify or "skills@latest list" in verify
        assert not re.search(r"^npx .*--version", verify, re.M)
        if "@kisev/agentomatic" in install:
            assert "npm list " in verify
            assert "npm list --global @kisev/agentomatic" not in verify
        if "skills@latest add" in install:
            assert "skills@latest list" in verify
            assert "skills@dev" not in preview + install + verify
            assert (" list --global" in verify) == (" add " in install and "--global" in install)


def test_complete_setup_checks_every_installed_application() -> None:
    for block, channel in zip(installation_blocks("README.md"), ("latest", "dev"), strict=True):
        for name in ("agentomatic", "memomatic", "reviewmatic", "taskmatic"):
            assert f"npm view --prefer-online @kisev/{name}@{channel} version" in block
        for name in ("memomatic", "reviewmatic", "taskmatic"):
            assert f"{name} --version" in block
        assert 'npm list --prefix "$HOME/.config/opencode" @kisev/agentomatic --depth=0' in block
        assert (
            "npm list --global @kisev/memomatic @kisev/reviewmatic @kisev/taskmatic --depth=0"
            in block
        )
