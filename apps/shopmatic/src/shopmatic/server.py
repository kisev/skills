"""MCP stdio server exposing shopmatic search, product, and compare tools.

The server speaks newline-delimited JSON-RPC 2.0 on stdin/stdout, matching
the MCP stdio transport. Every tool answer is a unified-schema JSON payload;
errors are reported as tool-level error results, never as bare exceptions.
"""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from shopmatic import __version__
from shopmatic.errors import InvalidInput, ShopmaticError
from shopmatic.marketplaces import REGISTRY
from shopmatic.models import MarketplaceResult
from shopmatic.service import Shopmatic

PROTOCOL_VERSION = "2025-06-18"
MAX_REQUEST_BYTES = 1_000_000

TOOL_NAMES = ("shopmatic_search", "shopmatic_product", "shopmatic_compare")


def _marketplace_enum() -> list[str]:
    return sorted(REGISTRY)


def _tool_definitions() -> list[dict[str, object]]:
    description = (
        "Marketplace name. wildberries and yandex-market passed the agent-browser "
        "spike; ozon is blocked by its antibot challenge and answers an explicit error."
    )
    return [
        {
            "name": "shopmatic_search",
            "description": (
                "Search a marketplace and return structured products "
                "(name, price, URL, rating) in the unified shopmatic schema."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["marketplace", "query"],
                "properties": {
                    "marketplace": {
                        "type": "string",
                        "enum": _marketplace_enum(),
                        "description": description,
                    },
                    "query": {"type": "string", "minLength": 1, "maxLength": 200},
                    "max_price": {"type": "number", "exclusiveMinimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "anonymous": {"type": "boolean", "default": True},
                },
            },
        },
        {
            "name": "shopmatic_product",
            "description": (
                "Fetch one product card (name, price, URL, rating) from a marketplace."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["marketplace", "product"],
                "properties": {
                    "marketplace": {
                        "type": "string",
                        "enum": _marketplace_enum(),
                        "description": description,
                    },
                    "product": {
                        "type": "string",
                        "description": "Marketplace product id or full product URL.",
                    },
                    "anonymous": {"type": "boolean", "default": True},
                },
            },
        },
        {
            "name": "shopmatic_compare",
            "description": (
                "Search the same query on several marketplaces and return the "
                "top results of each in the unified schema for side-by-side comparison."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 200},
                    "marketplaces": {
                        "type": "array",
                        "items": {"type": "string", "enum": _marketplace_enum()},
                        "default": ["wildberries", "yandex-market"],
                    },
                    "max_price": {"type": "number", "exclusiveMinimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "anonymous": {"type": "boolean", "default": True},
                },
            },
        },
    ]


def _argument_mapping(arguments: object) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise InvalidInput("tool arguments must be an object")
    return arguments


def _string_argument(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str):
        raise InvalidInput(f"{key} must be a string")
    return value


def _optional_float(arguments: dict[str, Any], key: str) -> float | None:
    value = arguments.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidInput(f"{key} must be a number")
    return float(value)


def _optional_int(arguments: dict[str, Any], key: str, default: int) -> int:
    value = arguments.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidInput(f"{key} must be an integer")
    return int(value)


def _optional_bool(arguments: dict[str, Any], key: str, default: bool) -> bool:
    value = arguments.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise InvalidInput(f"{key} must be a boolean")
    return value


class ShopmaticServer:
    """JSON-RPC dispatcher around one Shopmatic service instance."""

    def __init__(self, service: Shopmatic | None = None) -> None:
        self.service = service or Shopmatic()

    def handle_request(self, request: dict[str, object]) -> dict[str, object] | None:
        """Dispatch one JSON-RPC request; notifications answer None."""
        method = request.get("method")
        request_id = request.get("id")
        if not isinstance(method, str):
            return _error_response(request_id, -32600, "request has no method")
        if "id" not in request:
            return None  # notification
        try:
            result = self._dispatch(method, request.get("params"))
        except ShopmaticError as exc:
            return _error_response(request_id, -32000, str(exc))
        except KeyError as exc:
            return _error_response(request_id, -32601, str(exc.args[0] if exc.args else exc))
        return _result_response(request_id, result)

    def _dispatch(self, method: str, params: object) -> dict[str, object]:
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "shopmatic", "version": __version__},
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": _tool_definitions()}
        if method == "tools/call":
            return self._call_tool(params)
        raise KeyError(f"method {method!r} is not supported")

    def _call_tool(self, params: object) -> dict[str, object]:
        mapping = _argument_mapping(params)
        name = _string_argument(mapping, "name")
        arguments = _argument_mapping(mapping.get("arguments"))
        try:
            text = self._run_tool(name, arguments)
        except ShopmaticError as exc:
            return {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            }
        return {"content": [{"type": "text", "text": text}], "isError": False}

    def _run_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "shopmatic_search":
            result = self.service.search(
                _string_argument(arguments, "marketplace"),
                _string_argument(arguments, "query"),
                max_price=_optional_float(arguments, "max_price"),
                limit=_optional_int(arguments, "limit", 10),
                anonymous=_optional_bool(arguments, "anonymous", True),
            )
            return result.to_json()
        if name == "shopmatic_product":
            item = self.service.product(
                _string_argument(arguments, "marketplace"),
                _string_argument(arguments, "product"),
                anonymous=_optional_bool(arguments, "anonymous", True),
            )
            return MarketplaceResult(
                marketplace=_string_argument(arguments, "marketplace"),
                kind="product",
                items=(item,),
            ).to_json()
        if name == "shopmatic_compare":
            names = arguments.get("marketplaces")
            if names is not None and not isinstance(names, list):
                raise InvalidInput("marketplaces must be an array")
            results = self.service.compare(
                _string_argument(arguments, "query"),
                [str(entry) for entry in names] if names else [],
                max_price=_optional_float(arguments, "max_price"),
                limit=_optional_int(arguments, "limit", 5),
                anonymous=_optional_bool(arguments, "anonymous", True),
            )
            return json.dumps(
                {
                    "schema": "kisev-skills/shopmatic-result/v1",
                    "kind": "compare",
                    "comparisons": [entry.to_dict() for entry in results],
                },
                ensure_ascii=False,
                indent=1,
            )
        raise InvalidInput(f"unknown tool {name!r}")


def _result_response(request_id: object, result: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error_response(request_id: object, code: int, message: str) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Run the stdio loop until stdin closes."""
    input_stream = stdin if stdin is not None else sys.stdin
    output_stream = stdout if stdout is not None else sys.stdout
    server = ShopmaticServer()
    for raw_line in iter(input_stream.readline, ""):
        line = raw_line.strip()
        if not line:
            continue
        response: dict[str, object] | None
        if len(line) > MAX_REQUEST_BYTES:
            response = _error_response(None, -32700, "request is too large")
        else:
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                response = _error_response(None, -32700, "request is not valid JSON")
            else:
                if not isinstance(request, dict):
                    response = _error_response(None, -32600, "request is not an object")
                else:
                    response = server.handle_request(request)
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()
    return 0
