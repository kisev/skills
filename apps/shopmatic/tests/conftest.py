"""Make the src-layout package importable and provide the fake browser fixtures."""

from __future__ import annotations

import stat
import sys
import textwrap
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FAKE_SCRIPT = textwrap.dedent(
    """
    #!/usr/bin/env python3
    import json, os, sys, time

    COMMANDS = {"cookies", "open", "wait", "scroll", "eval", "close"}
    args = sys.argv[1:]
    command = next((a for a in args if a in COMMANDS), "unknown")
    scenario = os.environ.get("SHOPMATIC_FAKE_SCENARIO", "ok")
    log = os.environ.get("SHOPMATIC_FAKE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(args) + "\\n")

    if command == "close":
        sys.exit(0)
    if command == "cookies":
        empty = scenario != "anon_fail"
        print(json.dumps({"success": True, "data": {"cookies": [] if empty else [
            {"name": "session", "value": "host"}]}}))
        sys.exit(0)
    if command == "wait":
        if scenario == "timeout":
            time.sleep(5)
        time.sleep(0.05)
        sys.exit(0)
    if command in {"open", "scroll"}:
        if scenario == "open_fail":
            print("boom", file=sys.stderr)
            sys.exit(3)
        sys.exit(0)
    if command == "eval":
        script = sys.stdin.read()
        if scenario == "eval_fail":
            print("eval boom", file=sys.stderr)
            sys.exit(4)
        if "Подозрительная" in script:
            state = {"blocked": scenario == "blocked", "cards": 0 if scenario == "never_render" else 40}
            print(json.dumps(json.dumps(state), ensure_ascii=False))
        elif "SmartCaptcha" in script:
            state = {"captcha": scenario == "blocked", "cards": 0 if scenario == "never_render" else 8}
            print(json.dumps(json.dumps(state), ensure_ascii=False))
        elif "product-card" in script and "forEach" in script:
            items = [{
                "id": "123", "name": "Клавиатура тест", "price": 999.0, "old_price": 1500,
                "rating": 4.5, "rating_votes": 12, "url": "https://www.wildberries.ru/catalog/123/detail.aspx",
            }]
            print(json.dumps(json.dumps({"items": items}), ensure_ascii=False))
        elif "snippet-link" in script:
            items = [{
                "id": "456", "name": "Клавиатура ЯМ", "price": 1234, "old_price": None,
                "rating": 4.0, "rating_votes": None, "url": "https://market.yandex.ru/card/x/456",
            }]
            print(json.dumps(json.dumps({"items": items}), ensure_ascii=False))
        elif "купить" in script:
            payload = {"id": "123", "name": "Карточка WB", "price": 777, "old_price": 1000,
                       "rating": 4.8, "rating_votes": 500,
                       "url": "https://www.wildberries.ru/catalog/123/detail.aspx"}
            print(json.dumps(json.dumps(payload), ensure_ascii=False))
        elif "application/ld+json" in script:
            payload = {"id": "456", "name": "Карточка ЯМ", "price": 888, "old_price": None,
                       "rating": 4.1, "rating_votes": None,
                       "url": "https://market.yandex.ru/card/x/456"}
            print(json.dumps(json.dumps(payload), ensure_ascii=False))
        else:
            print(json.dumps(json.dumps({"items": []})))
        sys.exit(0)
    print("unknown command", file=sys.stderr)
    sys.exit(9)
    """
)


@pytest.fixture
def fake_browser(tmp_path: Path) -> Path:
    """Install a scripted fake agent-browser executable and return its path."""
    executable = tmp_path / "fake-agent-browser"
    executable.write_text(FAKE_SCRIPT.lstrip(), encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


@pytest.fixture
def fake_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Route profiles into the test tree and reset fake scenarios."""
    root = tmp_path / "profiles"
    monkeypatch.setenv("SHOPMATIC_PROFILE_ROOT", str(root))
    monkeypatch.delenv("SHOPMATIC_FAKE_SCENARIO", raising=False)
    return root


@pytest.fixture
def fake_cli(
    monkeypatch: pytest.MonkeyPatch,
    fake_browser: Path,
    fake_environment: Path,
) -> Path:
    """Point the CLI-level SHOPMATIC_AGENT_BROWSER override at the fake."""
    monkeypatch.setenv("SHOPMATIC_AGENT_BROWSER", str(fake_browser))
    return fake_browser
