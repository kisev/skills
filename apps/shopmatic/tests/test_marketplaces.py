"""Marketplace registry and unified-schema parsing tests."""

from __future__ import annotations

import json

import pytest

from shopmatic.errors import ExtractionFailed, InvalidInput
from shopmatic.marketplaces import OZON, REGISTRY, _unwrap_payload, resolve


def test_resolve_is_case_insensitive_and_rejects_unknown() -> None:
    assert resolve(" Wildberries ").name == "wildberries"
    with pytest.raises(InvalidInput, match="unknown marketplace"):
        resolve("avito")


def test_ozon_is_registered_but_blocked() -> None:
    assert OZON.available is False
    assert OZON.blocker is not None
    assert "spike" in OZON.blocker
    assert set(REGISTRY) == {"wildberries", "yandex-market", "ozon"}


def test_search_urls_quote_and_bound_price() -> None:
    wb = resolve("wildberries")
    assert wb.build_search_url("клавиатура", "5000") == (
        "https://www.wildberries.ru/catalog/0/search.aspx"
        "?search=%D0%BA%D0%BB%D0%B0%D0%B2%D0%B8%D0%B0%D1%82%D1%83%D1%80%D0%B0"
        "&price=;5000&sort=priceup"
    )
    ym = resolve("yandex-market")
    assert ym.build_search_url("клавиатура", "5000") == (
        "https://market.yandex.ru/search?text=%D0%BA%D0%BB%D0%B0%D0%B2%D0%B8%D0%B0%D1%82%D1%83%D1%80%D0%B0"
        "&price=;5000"
    )


def test_unwrap_payload_decodes_double_encoded_json() -> None:
    inner = json.dumps({"items": []})
    assert _unwrap_payload(json.dumps(inner)) == {"items": []}
    with pytest.raises(ExtractionFailed, match="not JSON"):
        _unwrap_payload("not json")
    with pytest.raises(ExtractionFailed, match="not an object"):
        _unwrap_payload(json.dumps([1, 2]))


def make_raw(payload: dict[str, object]) -> str:
    return json.dumps(json.dumps(payload), ensure_ascii=False)


def test_parse_items_builds_unified_rows() -> None:
    wb = resolve("wildberries")
    raw = make_raw(
        {
            "items": [
                {
                    "id": "1",
                    "name": " Товар А ",
                    "price": 100.0,
                    "old_price": 150,
                    "rating": 4.5,
                    "rating_votes": 10,
                    "url": "https://www.wildberries.ru/catalog/1/detail.aspx",
                },
                {
                    "id": "2",
                    "name": "Товар Б",
                    "price": None,
                    "rating": 9,
                    "rating_votes": -3,
                    "url": "https://www.wildberries.ru/catalog/2/detail.aspx",
                },
                {"name": "no url", "price": 1},
                {"url": "https://www.wildberries.ru/catalog/3/detail.aspx"},
            ]
        }
    )
    result = wb.parse_items(raw, kind="search", query="тест", limit=10)
    assert result.marketplace == "wildberries"
    assert result.kind == "search"
    assert result.query == "тест"
    assert [item.position for item in result.items] == [1, 2]
    first, second = result.items
    assert first.name == "Товар А"
    assert first.price == 100.0
    assert first.old_price == 150
    assert first.rating == 4.5
    assert first.rating_votes == 10
    assert second.price is None
    assert second.rating is None
    assert second.rating_votes is None


def test_parse_items_respects_limit() -> None:
    wb = resolve("wildberries")
    raw = make_raw(
        {
            "items": [
                {
                    "name": f"item {index}",
                    "url": f"https://www.wildberries.ru/catalog/{index}/detail.aspx",
                }
                for index in range(10)
            ]
        }
    )
    result = wb.parse_items(raw, kind="search", query=None, limit=3)
    assert len(result.items) == 3


def test_parse_items_rejects_missing_list() -> None:
    wb = resolve("wildberries")
    with pytest.raises(ExtractionFailed, match="no items"):
        wb.parse_items(make_raw({"other": []}), kind="search", query=None, limit=10)


def test_parse_product_builds_item() -> None:
    ym = resolve("yandex-market")
    raw = make_raw(
        {
            "id": "456",
            "name": "Карточка",
            "price": 888,
            "old_price": None,
            "rating": 4.1,
            "rating_votes": None,
            "url": "https://market.yandex.ru/card/x/456",
        }
    )
    item = ym.parse_product(raw)
    assert item.position == 1
    assert item.id == "456"
    assert item.price == 888.0
    assert item.currency == "RUB"


def test_parse_product_requires_name_and_url() -> None:
    ym = resolve("yandex-market")
    with pytest.raises(ExtractionFailed, match="no name"):
        ym.parse_product(make_raw({"url": "https://market.yandex.ru/card/x/1"}))
    with pytest.raises(ExtractionFailed, match="no URL"):
        ym.parse_product(make_raw({"name": "x"}))


def test_product_url_accepts_full_url() -> None:
    ym = resolve("yandex-market")
    url = "https://market.yandex.ru/card/slug/123?ogV=1"
    assert ym.build_product_url(url) == url
    assert ym.build_product_url("123").startswith("https://market.yandex.ru/card/123")
