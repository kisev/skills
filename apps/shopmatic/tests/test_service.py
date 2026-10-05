"""Service orchestration tests: anonymity, rendering, and blocked marketplaces."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from shopmatic.errors import AnonymityViolated, InvalidInput, MarketplaceBlocked, RenderFailed
from shopmatic.service import Shopmatic


def make_service(fake_browser: Path) -> Shopmatic:
    return Shopmatic(headed=False, browser_executable=str(fake_browser))


def test_search_returns_unified_result_and_discards_profile(
    fake_browser: Path,
    fake_environment: Path,
) -> None:
    service = make_service(fake_browser)
    result = service.search("wildberries", "клавиатура", max_price=5000, limit=10)
    assert result.marketplace == "wildberries"
    assert result.items[0].name == "Клавиатура тест"
    assert result.items[0].price == 999.0
    assert result.items[0].currency == "RUB"
    anonymous_root = fake_environment / "anonymous"
    assert not anonymous_root.exists() or list(anonymous_root.iterdir()) == []


def test_search_yandex_market(fake_browser: Path, fake_environment: Path) -> None:
    service = make_service(fake_browser)
    result = service.search("yandex-market", "клавиатура")
    assert result.items[0].name == "Клавиатура ЯМ"
    assert result.items[0].url.startswith("https://market.yandex.ru/card/")


def test_search_fails_when_profile_not_empty(
    fake_browser: Path,
    fake_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHOPMATIC_FAKE_SCENARIO", "anon_fail")
    service = make_service(fake_browser)
    with pytest.raises(AnonymityViolated, match="not empty"):
        service.search("wildberries", "клавиатура")
    anonymous_root = fake_environment / "anonymous"
    assert not anonymous_root.exists() or list(anonymous_root.iterdir()) == []


def test_blocked_marketplace_answers_explicitly(fake_browser: Path) -> None:
    service = make_service(fake_browser)
    with pytest.raises(MarketplaceBlocked, match="spike"):
        service.search("ozon", "клавиатура")


def test_render_failure_is_explicit(
    fake_browser: Path,
    fake_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHOPMATIC_FAKE_SCENARIO", "never_render")
    service = make_service(fake_browser)
    with pytest.raises(RenderFailed, match="did not render"):
        service.search("wildberries", "клавиатура")


def test_antibot_challenge_is_explicit(
    fake_browser: Path,
    fake_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHOPMATIC_FAKE_SCENARIO", "blocked")
    service = make_service(fake_browser)
    with pytest.raises(RenderFailed, match="antibot"):
        service.search("yandex-market", "клавиатура")


def test_product_card(fake_browser: Path, fake_environment: Path) -> None:
    service = make_service(fake_browser)
    item = service.product("wildberries", "123")
    assert item.name == "Карточка WB"
    assert item.price == 777.0


def test_account_mode_keeps_profile(
    fake_browser: Path,
    fake_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHOPMATIC_FAKE_SCENARIO", "anon_fail")
    service = make_service(fake_browser)
    result = service.search("wildberries", "клавиатура", anonymous=False)
    assert result.items
    assert (fake_environment / "accounts" / "wildberries").is_dir()


def test_invalid_inputs_rejected_before_browser(
    fake_browser: Path,
    fake_environment: Path,
) -> None:
    service = make_service(fake_browser)
    with pytest.raises(InvalidInput, match="query"):
        service.search("wildberries", "   ")
    with pytest.raises(InvalidInput, match="max_price"):
        service.search("wildberries", "т", max_price=-5)
    with pytest.raises(InvalidInput, match="limit"):
        service.search("wildberries", "т", limit=0)


def test_compare_deduplicates_marketplaces(
    fake_browser: Path,
    fake_environment: Path,
) -> None:
    service = make_service(fake_browser)
    results = service.compare("клавиатура", ["wildberries", "wildberries", "yandex-market"])
    assert [entry.marketplace for entry in results] == ["wildberries", "yandex-market"]
    assert all(entry.kind == "search" for entry in results)


def test_login_uses_persistent_profile(
    fake_browser: Path,
    fake_environment: Path,
) -> None:
    service = make_service(fake_browser)
    profile = service.open_login("wildberries")
    assert profile == fake_environment / "accounts" / "wildberries"
    assert profile.is_dir()


def test_browser_executable_env_is_respected(
    fake_browser: Path,
    fake_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHOPMATIC_AGENT_BROWSER", str(fake_browser))
    service = Shopmatic()
    result = service.search("wildberries", "клавиатура")
    assert result.items
    assert "SHOPMATIC_AGENT_BROWSER" in os.environ
