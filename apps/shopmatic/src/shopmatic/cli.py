"""Shopmatic command-line surface: serve, search, product, compare, login."""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

from shopmatic import __version__
from shopmatic.errors import InvalidInput, ShopmaticError
from shopmatic.marketplaces import REGISTRY
from shopmatic.models import MarketplaceResult
from shopmatic.server import serve
from shopmatic.service import Shopmatic

if TYPE_CHECKING:
    from collections.abc import Sequence

PROGRAM_DESCRIPTION = "Marketplace shopping research through agent-browser"
MARKETPLACE_NAMES = sorted(REGISTRY)
DEFAULT_COMPARISON = ["wildberries", "yandex-market"]


def build_parser() -> argparse.ArgumentParser:
    """Build the shopmatic argument parser."""
    parser = argparse.ArgumentParser(prog="shopmatic", description=PROGRAM_DESCRIPTION)
    parser.add_argument("--version", action="version", version=f"shopmatic {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="run the MCP stdio server")
    serve.add_argument(
        "--headed",
        action="store_true",
        help="run the browser with a visible window (needs a display)",
    )

    search = subparsers.add_parser("search", help="search one marketplace")
    search.add_argument("marketplace", choices=MARKETPLACE_NAMES)
    search.add_argument("query")
    search.add_argument("--max-price", type=float, default=None)
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--headed", action="store_true")
    search.add_argument(
        "--account",
        action="store_true",
        help="use the persistent logged-in profile instead of anonymous",
    )

    product = subparsers.add_parser("product", help="fetch one product card")
    product.add_argument("marketplace", choices=MARKETPLACE_NAMES)
    product.add_argument("product", help="product id or full product URL")
    product.add_argument("--headed", action="store_true")
    product.add_argument("--account", action="store_true")

    compare = subparsers.add_parser("compare", help="search one query on several marketplaces")
    compare.add_argument("query")
    compare.add_argument(
        "--marketplaces",
        default=",".join(DEFAULT_COMPARISON),
        help=f"comma-separated; default: {','.join(DEFAULT_COMPARISON)}",
    )
    compare.add_argument("--max-price", type=float, default=None)
    compare.add_argument("--limit", type=int, default=5)
    compare.add_argument("--headed", action="store_true")
    compare.add_argument("--account", action="store_true")

    login = subparsers.add_parser("login", help="open a headed browser for manual login")
    login.add_argument("marketplace", choices=MARKETPLACE_NAMES)

    return parser


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1))


def _run(args: argparse.Namespace) -> int:
    service = Shopmatic(headed=getattr(args, "headed", False))
    anonymous = not getattr(args, "account", False)
    if args.command == "search":
        _print(
            service.search(
                args.marketplace,
                args.query,
                max_price=args.max_price,
                limit=args.limit,
                anonymous=anonymous,
            ).to_dict()
        )
        return 0
    if args.command == "product":
        item = service.product(args.marketplace, args.product, anonymous=anonymous)
        _print(
            MarketplaceResult(
                marketplace=args.marketplace,
                kind="product",
                items=(item,),
            ).to_dict()
        )
        return 0
    if args.command == "compare":
        names = [name.strip() for name in args.marketplaces.split(",") if name.strip()]
        results = service.compare(
            args.query,
            names,
            max_price=args.max_price,
            limit=args.limit,
            anonymous=anonymous,
        )
        _print(
            {
                "schema": "kisev-skills/shopmatic-result/v1",
                "kind": "compare",
                "comparisons": [entry.to_dict() for entry in results],
            }
        )
        return 0
    if args.command == "login":
        profile = service.open_login(args.marketplace)
        print(f"log in by hand in the opened browser window; the profile is kept at {profile}")
        return 0
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: dispatch subcommands and map errors to exit codes."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        return serve()
    if args.command is None:
        parser.print_help()
        return 2
    try:
        return _run(args)
    except InvalidInput as exc:
        print(f"shopmatic: {exc}", file=sys.stderr)
        return 2
    except ShopmaticError as exc:
        print(f"shopmatic: {exc}", file=sys.stderr)
        return 1
    except (ValueError, KeyError) as exc:
        print(f"shopmatic: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
