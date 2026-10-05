"""MCP stdio server tests: JSON-RPC contract and tool answers."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from shopmatic.errors import InvalidInput
from shopmatic.models import ProductItem
from shopmatic.server import ShopmaticServer, serve
from shopmatic.service import Shopmatic


def request(method: str, params: object = None, request_id: int = 1) -> dict[str, object]:
    payload: dict[str, object] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return payload


def result_of(response: dict[str, object] | None) -> dict[str, object]:
    """Return the typed result object of a successful JSON-RPC response."""
    assert response is not None
    assert "result" in response, response
    return cast("dict[str, object]", response["result"])


def error_of(response: dict[str, object] | None) -> dict[str, object]:
    """Return the typed error object of a JSON-RPC error response."""
    assert response is not None
    assert "error" in response, response
    return cast("dict[str, object]", response["error"])


def text_of(result: dict[str, object]) -> str:
    """Return the text payload of a tool result."""
    content = cast("list[dict[str, object]]", result["content"])
    return str(content[0]["text"])


def test_initialize_returns_contract(fake_browser: Path) -> None:
    server = ShopmaticServer(Shopmatic(browser_executable=str(fake_browser)))
    response = server.handle_request(request("initialize", {"protocolVersion": "2025-06-18"}))
    result = result_of(response)
    assert result["protocolVersion"] == "2025-06-18"
    info = cast("dict[str, object]", result["serverInfo"])
    assert info["name"] == "shopmatic"
    assert "tools" in cast("dict[str, object]", result["capabilities"])


def test_notification_gets_no_response(fake_browser: Path) -> None:
    server = ShopmaticServer(Shopmatic(browser_executable=str(fake_browser)))
    assert server.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list_exposes_three_tools(fake_browser: Path) -> None:
    server = ShopmaticServer(Shopmatic(browser_executable=str(fake_browser)))
    response = server.handle_request(request("tools/list"))
    tools = cast("list[dict[str, object]]", result_of(response)["tools"])
    assert [tool["name"] for tool in tools] == [
        "shopmatic_search",
        "shopmatic_product",
        "shopmatic_compare",
    ]
    for tool in tools:
        schema = cast("dict[str, object]", tool["inputSchema"])
        assert schema["type"] == "object"


def test_ping_answers_empty_result(fake_browser: Path) -> None:
    server = ShopmaticServer(Shopmatic(browser_executable=str(fake_browser)))
    response = server.handle_request(request("ping"))
    assert result_of(response) == {}


def test_unknown_method_maps_to_32601(fake_browser: Path) -> None:
    server = ShopmaticServer(Shopmatic(browser_executable=str(fake_browser)))
    response = server.handle_request(request("resources/list"))
    assert error_of(response)["code"] == -32601


def test_search_tool_returns_unified_json(
    fake_browser: Path,
    fake_environment: Path,
) -> None:
    server = ShopmaticServer(Shopmatic(browser_executable=str(fake_browser)))
    response = server.handle_request(
        request(
            "tools/call",
            {
                "name": "shopmatic_search",
                "arguments": {
                    "marketplace": "wildberries",
                    "query": "клавиатура",
                    "max_price": 5000,
                },
            },
        )
    )
    result = result_of(response)
    assert result["isError"] is False
    payload = json.loads(text_of(result))
    assert payload["schema"] == "kisev-skills/shopmatic-result/v1"
    assert payload["items"][0]["name"] == "Клавиатура тест"


def test_blocked_marketplace_is_tool_error(
    fake_browser: Path,
    fake_environment: Path,
) -> None:
    server = ShopmaticServer(Shopmatic(browser_executable=str(fake_browser)))
    response = server.handle_request(
        request(
            "tools/call",
            {
                "name": "shopmatic_search",
                "arguments": {"marketplace": "ozon", "query": "клавиатура"},
            },
        )
    )
    result = result_of(response)
    assert result["isError"] is True
    assert "spike" in text_of(result)


def test_unknown_tool_is_tool_error(fake_browser: Path) -> None:
    server = ShopmaticServer(Shopmatic(browser_executable=str(fake_browser)))
    response = server.handle_request(
        request(
            "tools/call",
            {
                "name": "shopmatic_buy",
                "arguments": {},
            },
        )
    )
    result = result_of(response)
    assert result["isError"] is True
    assert "unknown tool" in text_of(result)


def test_compare_tool_wraps_marketplace_results(
    fake_browser: Path,
    fake_environment: Path,
) -> None:
    server = ShopmaticServer(Shopmatic(browser_executable=str(fake_browser)))
    response = server.handle_request(
        request(
            "tools/call",
            {
                "name": "shopmatic_compare",
                "arguments": {"query": "клавиатура", "max_price": 5000, "limit": 3},
            },
        )
    )
    payload = json.loads(text_of(result_of(response)))
    assert payload["kind"] == "compare"
    assert [entry["marketplace"] for entry in payload["comparisons"]] == [
        "wildberries",
        "yandex-market",
    ]


def test_product_tool_returns_single_item(
    fake_browser: Path,
    fake_environment: Path,
) -> None:
    server = ShopmaticServer(Shopmatic(browser_executable=str(fake_browser)))
    response = server.handle_request(
        request(
            "tools/call",
            {
                "name": "shopmatic_product",
                "arguments": {"marketplace": "wildberries", "product": "123"},
            },
        )
    )
    payload = json.loads(text_of(result_of(response)))
    assert payload["kind"] == "product"
    assert payload["items"][0]["name"] == "Карточка WB"


def test_invalid_arguments_raise_protocol_error(fake_browser: Path) -> None:
    server = ShopmaticServer(Shopmatic(browser_executable=str(fake_browser)))
    response = server.handle_request(request("tools/call", {"name": "shopmatic_search"}))
    assert error_of(response)["code"] == -32000


def test_standalone_invalid_input_error() -> None:
    with pytest.raises(InvalidInput, match="object"):
        raise InvalidInput("tool arguments must be an object")


def test_serve_loop_answers_lines(fake_browser: Path, fake_environment: Path) -> None:
    input_stream = io.StringIO(json.dumps(request("tools/list")) + "\n" + "not json\n")
    output_stream = io.StringIO()
    code = serve(stdin=input_stream, stdout=output_stream)
    assert code == 0
    lines = [json.loads(line) for line in output_stream.getvalue().splitlines()]
    assert len(lines) == 2
    assert lines[0]["result"]["tools"]
    assert lines[1]["error"]["code"] == -32700


def test_serve_ignores_blank_lines(fake_browser: Path) -> None:
    output_stream = io.StringIO()
    assert serve(stdin=io.StringIO("\n\n"), stdout=output_stream) == 0
    assert output_stream.getvalue() == ""


def test_product_item_schema_roundtrip() -> None:
    item = ProductItem(position=1, name="n", url="https://x", price=1.5)
    assert item.currency == "RUB"
