"""Browser driver tests: subprocess discipline against the fake executable."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from shopmatic.browser import AgentBrowser
from shopmatic.errors import BrowserTimeout, BrowserUnavailable


def make_browser(fake_browser: Path, tmp_path: Path, **kwargs: object) -> AgentBrowser:
    options: dict[str, object] = {"headed": False, "executable": str(fake_browser)}
    options.update(kwargs)
    return AgentBrowser("shopmatic-test", tmp_path / "profile", **options)  # type: ignore[arg-type]


def test_vector_is_bounded_without_shell(fake_browser: Path, tmp_path: Path) -> None:
    browser = make_browser(fake_browser, tmp_path)
    vector = browser._vector("open", "https://example.com")
    assert vector[0] == str(fake_browser)
    assert "--namespace" in vector and "shopmatic" in vector
    assert "--profile" in vector
    assert "--headed" not in vector
    assert "|" not in vector and ";" not in vector


def test_headed_flag_appended(fake_browser: Path, tmp_path: Path) -> None:
    browser = make_browser(fake_browser, tmp_path, headed=True)
    assert "--headed" in browser._vector("close")


def test_cookies_parses_payload(fake_browser: Path, tmp_path: Path) -> None:
    browser = make_browser(fake_browser, tmp_path)
    assert browser.cookies() == []


def test_run_failure_raises_unavailable(
    fake_browser: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHOPMATIC_FAKE_SCENARIO", "open_fail")
    browser = make_browser(fake_browser, tmp_path)
    with pytest.raises(BrowserUnavailable, match="open failed"):
        browser.open("https://example.com")


def test_timeout_raises_browser_timeout(fake_browser: Path, tmp_path: Path) -> None:
    browser = make_browser(fake_browser, tmp_path, executable=str(fake_browser))
    import os

    os.environ["SHOPMATIC_FAKE_SCENARIO"] = "timeout"
    try:
        with pytest.raises(BrowserTimeout):
            browser.run("wait", "5000", timeout=0.5)
    finally:
        os.environ.pop("SHOPMATIC_FAKE_SCENARIO", None)


def test_missing_executable_raises(tmp_path: Path) -> None:
    browser = AgentBrowser("shopmatic-test", tmp_path / "p", executable=str(tmp_path / "absent"))
    with pytest.raises(BrowserUnavailable, match="not runnable"):
        browser.cookies()


def test_evaluate_returns_raw_stdout(fake_browser: Path, tmp_path: Path) -> None:
    browser = make_browser(fake_browser, tmp_path)
    raw = browser.evaluate("(() => JSON.stringify({items: []}))()")
    payload = json.loads(json.loads(raw))
    assert payload == {"items": []}
