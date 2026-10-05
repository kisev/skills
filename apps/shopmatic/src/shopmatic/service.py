"""Shopmatic service: anonymous-first marketplace runs through agent-browser.

Every anonymous run launches a fresh empty profile, proves it is empty before
the first navigation, never signs in, and discards the profile afterwards.
Account mode reuses a persistent private profile that the user filled by hand.
"""

from __future__ import annotations

import secrets
import sys
from contextlib import suppress
from typing import TYPE_CHECKING

from shopmatic.browser import AgentBrowser
from shopmatic.errors import (
    AnonymityViolated,
    BrowserUnavailable,
    InvalidInput,
    MarketplaceBlocked,
    RenderFailed,
    ShopmaticError,
)
from shopmatic.marketplaces import Marketplace, _unwrap_payload, resolve
from shopmatic.models import (
    MarketplaceResult,
    ProductItem,
    validate_limit,
    validate_max_price,
    validate_query,
)
from shopmatic.profile import account_profile, anonymous_profile, discard_profile

if TYPE_CHECKING:
    from pathlib import Path


class Shopmatic:
    """Facade for search, product, and compare operations."""

    def __init__(self, *, headed: bool = False, browser_executable: str | None = None) -> None:
        self.headed = headed
        self.browser_executable = browser_executable

    def search(
        self,
        marketplace_name: str,
        query: str,
        *,
        max_price: float | None = None,
        limit: int = 10,
        anonymous: bool = True,
    ) -> MarketplaceResult:
        """Search one marketplace and return structured results."""
        marketplace = self._require_available(marketplace_name)
        clean_query = validate_query(query)
        clean_price = validate_max_price(max_price)
        clean_limit = validate_limit(limit)

        with self._session(marketplace.name, anonymous) as browser:
            browser.open(marketplace.build_search_url(clean_query, _price_fragment(clean_price)))
            self._wait_rendered(browser, marketplace)
            if marketplace.lazy_scroll:
                browser.scroll("down", 1500)
                browser.settle(2500)
                browser.scroll("up", 1500)
                browser.settle(1500)
            raw = browser.evaluate(marketplace.extract_js)
        result = marketplace.parse_items(raw, kind="search", query=clean_query, limit=clean_limit)
        if marketplace.lazy_scroll and result.items:
            rated = sum(1 for item in result.items if item.rating is not None)
            if rated == 0:
                result = result.with_warnings("ratings were not rendered yet; they may be missing")
        return result

    def product(
        self,
        marketplace_name: str,
        product_ref: str,
        *,
        anonymous: bool = True,
    ) -> ProductItem:
        """Fetch one product card from a marketplace."""
        marketplace = self._require_available(marketplace_name)
        reference = product_ref.strip()
        if not reference:
            raise InvalidInput("product reference must not be empty")

        with self._session(marketplace.name, anonymous) as browser:
            browser.open(marketplace.build_product_url(reference))
            browser.settle(4000)
            raw = browser.evaluate(marketplace.product_js)
        return marketplace.parse_product(raw)

    def compare(
        self,
        query: str,
        marketplaces: list[str],
        *,
        max_price: float | None = None,
        limit: int = 5,
        anonymous: bool = True,
    ) -> list[MarketplaceResult]:
        """Search the same query on several marketplaces."""
        clean_query = validate_query(query)
        names = marketplaces or ["wildberries", "yandex-market"]
        unique: list[str] = []
        for name in names:
            resolved = resolve(name).name
            if resolved not in unique:
                unique.append(resolved)
        return [
            self.search(
                name,
                clean_query,
                max_price=max_price,
                limit=limit,
                anonymous=anonymous,
            )
            for name in unique
        ]

    def open_login(self, marketplace_name: str) -> Path:
        """Open a headed browser on the persistent profile for manual login."""
        marketplace = resolve(marketplace_name)
        profile = account_profile(marketplace.name)
        browser = AgentBrowser(
            f"shopmatic-{marketplace.name}",
            profile,
            headed=True,
            executable=self.browser_executable,
        )
        browser.open(f"https://{marketplace.host}/")
        return profile

    def _require_available(self, marketplace_name: str) -> Marketplace:
        marketplace = resolve(marketplace_name)
        if not marketplace.available:
            raise MarketplaceBlocked(
                marketplace.blocker or f"{marketplace.display_name} is unavailable"
            )
        return marketplace

    def _session(self, marketplace_name: str, anonymous: bool) -> _BrowserSession:
        if anonymous:
            token = secrets.token_hex(8)
            profile = anonymous_profile(f"anon-{token}")
            session = f"shopmatic-{marketplace_name}-{token}"
            pre_close = False
        else:
            profile = account_profile(marketplace_name)
            session = f"shopmatic-{marketplace_name}"
            pre_close = True
        browser = AgentBrowser(
            session,
            profile,
            headed=self.headed,
            executable=self.browser_executable,
        )
        return _BrowserSession(browser, profile, anonymous, pre_close)

    def _wait_rendered(self, browser: AgentBrowser, marketplace: Marketplace) -> None:
        for _ in range(8):
            browser.settle(4000)
            raw = browser.evaluate(marketplace.probe_js)
            state = _probe_state(raw)
            blocked = bool(state.get("blocked") or state.get("captcha"))
            if blocked:
                raise RenderFailed(
                    f"{marketplace.display_name} answered with an antibot challenge page"
                )
            cards = state.get("cards")
            if isinstance(cards, int) and cards >= 5:
                return
        raise RenderFailed(f"{marketplace.display_name} did not render search results in time")


class _BrowserSession:
    """Bounded browser session that proves anonymity and cleans up after."""

    def __init__(
        self,
        browser: AgentBrowser,
        profile: Path,
        anonymous: bool,
        pre_close: bool,
    ) -> None:
        self.browser = browser
        self.profile = profile
        self.anonymous = anonymous
        self.pre_close = pre_close

    def __enter__(self) -> AgentBrowser:
        try:
            if self.pre_close:
                # Account sessions reuse a stable name; stop any stale browser
                # so the persistent profile is reopened cleanly. The
                # suppression absorbs the daemon shutdown race after a close.
                with suppress(BrowserUnavailable):
                    self.browser.close()
            if self.anonymous:
                cookies = self.browser.cookies()
                if cookies:
                    raise AnonymityViolated(
                        "fresh profile was not empty before the first navigation"
                    )
        except BaseException:
            self._cleanup()
            raise
        return self.browser

    def __exit__(self, *_exc: object) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        with suppress(BrowserUnavailable):
            self.browser.close()
        if not self.anonymous:
            return
        try:
            discard_profile(self.profile)
        except (OSError, ShopmaticError):
            # A discard failure must not mask the operation error that is
            # already propagating; standalone cleanup failures stay visible.
            if sys.exc_info()[0] is None:
                raise


def _price_fragment(max_price: float | None) -> str:
    return str(int(max_price)) if max_price is not None else ""


def _probe_state(raw: str) -> dict[str, object]:
    try:
        return _unwrap_payload(raw)
    except Exception:
        return {}
