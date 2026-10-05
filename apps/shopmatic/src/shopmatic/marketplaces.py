"""Marketplace registry: search URLs, render probes, and extraction payloads.

Every adapter returns the unified result schema. Only marketplaces that
passed the agent-browser spike are marked available; a failed marketplace
stays registered with its blocker so tools answer explicitly instead of
pretending support.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote

from shopmatic.errors import ExtractionFailed, InvalidInput
from shopmatic.models import (
    MarketplaceResult,
    ProductItem,
    parse_price,
    parse_rating,
    parse_rating_votes,
)

if TYPE_CHECKING:
    from collections.abc import Callable

RENDER_PROBES = 8
PROBE_SETTLE_MS = 4000
LAZY_SCROLL_PIXELS = 1500

WILDBERRIES_EXTRACT_JS = """
(() => {
  const parse = (el) => {
    if (!el) return null;
    const m = el.textContent.replace(/[\\u00a0\\u2009\\s]/g, "").match(/^(\\d+(?:[.,]\\d+)?)/);
    return m ? Number(m[1].replace(",", ".")) || null : null;
  };
  const out = [];
  document.querySelectorAll("article.product-card").forEach((card) => {
    if (out.length >= 50) return;
    const link = card.querySelector("a[data-testid='product-card-link']");
    const nameEl = card.querySelector("[data-testid='productName']");
    const priceEl = card.querySelector("ins[data-testid='product-card-current-price']");
    const oldEl = card.querySelector("del");
    const ratingEl = card.querySelector("[class*='rating']");
    if (!link || !nameEl) return;
    const ratingText = ratingEl ? ratingEl.textContent.trim() : "";
    const votes = ratingText.match(/[\\d\\s\\u00a0]+(?=\\s*оцен)/);
    out.push({
      id: card.getAttribute("data-nm-id"),
      name: nameEl.textContent.trim(),
      price: parse(priceEl),
      old_price: parse(oldEl),
      rating: ratingText ? Number(ratingText.match(/^(\\d+(?:[.,]\\d+)?)/)?.[1]?.replace(",", ".")) || null : null,
      rating_votes: votes ? Number(votes[0].replace(/[\\s\\u00a0]/g, "")) || null : null,
      url: link.href,
    });
  });
  return JSON.stringify({items: out});
})()
"""

WILDBERRIES_PROBE_JS = """
(() => JSON.stringify({blocked: document.body.innerText.includes("Подозрительная"),
  cards: document.querySelectorAll("article.product-card").length}))()
"""

WILDBERRIES_PRODUCT_JS = """
(() => {
  const parse = (el) => {
    if (!el) return null;
    const m = el.textContent.replace(/[\\u00a0\\u2009\\s]/g, "").match(/(\\d+(?:[.,]\\d+)?)/);
    return m ? Number(m[1].replace(",", ".")) || null : null;
  };
  const id = location.pathname.match(/catalog\\/(\\d+)/)?.[1] || null;
  const info = id ? document.querySelector(`[data-testid='${id}']`) : null;
  const scope = info || document.body;
  const text = scope.innerText || "";
  const title = document.title || "";
  const name = info
    ? (text.split("\\n")[0] || "").trim()
    : (title.split(/\\s+\\d+\\s+купить/)[0] || "").trim();
  const ratingMatch = text.match(/([\\d.,]+)\\s*\\n?\\s*\\d[\\d\\s\\u00a0]*оцен/) || text.match(/Рейтинг[:\\s]*([\\d.,]+)/);
  const votesMatch = text.match(/(\\d[\\d\\s\\u00a0]*)\\s*оцен/);
  return JSON.stringify({
    id,
    name,
    price: parse(scope.querySelector("ins")),
    old_price: parse(scope.querySelector("del")),
    rating: ratingMatch ? Number(ratingMatch[1].replace(",", ".")) || null : null,
    rating_votes: votesMatch ? Number(votesMatch[1].replace(/[\\s\\u00a0]/g, "")) || null : null,
    url: location.origin + location.pathname,
  });
})()
"""

YANDEX_PROBE_JS = """
(() => JSON.stringify({
  captcha: /SmartCaptcha|Подтвердите, что запросы отправляли вы|Доступ ограничен/i.test(
    document.body.innerText + document.title),
  cards: document.querySelectorAll("[data-auto='SerpList'] a[data-auto='snippet-link']").length}))()
"""

YANDEX_EXTRACT_JS = """
(() => {
  const parseNumber = (text) => {
    const m = text.replace(/[\\u00a0\\u2009\\s]/g, "").match(/(\\d+(?:[.,]\\d+)?)/);
    return m ? Number(m[1].replace(",", ".")) || null : null;
  };
  const serp = document.querySelector("[data-auto='SerpList']");
  if (!serp) return JSON.stringify({items: []});
  const out = [];
  const seenTiles = new Set();
  const seenUrls = new Set();
  for (const link of serp.querySelectorAll("a[data-auto='snippet-link'][href*='/card/']")) {
    let tile = link;
    for (let up = 0; up < 10 && tile !== serp; up++) {
      tile = tile.parentElement;
      if ((tile.innerText || "").includes("₽")) break;
    }
    if (seenTiles.has(tile)) continue;
    seenTiles.add(tile);
    const url = "https://market.yandex.ru" +
      new URL(link.getAttribute("href"), location.origin).pathname;
    if (seenUrls.has(url)) continue;
    seenUrls.add(url);
    if (out.length >= 50) break;
    const nameEl = tile.querySelector("[itemprop='name'], [data-auto='snippet-title']");
    const ratingMatch = (tile.innerText || "").match(/Рейтинг товара:\\s*([\\d.,]+)/);
    const prices = [...(tile.innerText || "").matchAll(/([\\d\\u00a0\\u2009\\s]{2,})\\s*₽/g)]
      .map((m) => parseNumber(m[1]));
    out.push({
      id: url.match(/\\/(\\d+)(?:\\?|$)/)?.[1] || null,
      name: nameEl ? nameEl.textContent.trim() : null,
      price: prices.length ? prices[prices.length - 1] : null,
      old_price: null,
      rating: ratingMatch ? Number(ratingMatch[1].replace(",", ".")) || null : null,
      rating_votes: null,
      url,
    });
  }
  return JSON.stringify({items: out});
})()
"""

YANDEX_PRODUCT_JS = """
(() => {
  const metaContent = (prop) => {
    const el = document.querySelector(`meta[itemprop='${prop}']`);
    return el ? (el.getAttribute("content") || "").trim() : "";
  };
  const name = metaContent("name") ||
    (document.querySelector("h1") ? document.querySelector("h1").textContent.trim() : "");
  let price = null;
  let oldPrice = null;
  let rating = null;
  let votes = null;
  for (const script of document.querySelectorAll("script[type='application/ld+json']")) {
    try {
      const data = JSON.parse(script.textContent);
      const products = Array.isArray(data) ? data : [data];
      for (const entry of products) {
        if (!entry || entry["@type"] !== "Product") continue;
        if (entry.offers && entry.offers.price != null) price = Number(entry.offers.price) || null;
        const high = entry.offers && entry.offers.highPrice;
        if (price == null && high != null) price = Number(high) || null;
        const aggregate = entry.aggregateRating;
        if (aggregate) {
          rating = aggregate.ratingValue != null ? Number(aggregate.ratingValue) || null : null;
          votes = aggregate.ratingCount != null ? Number(aggregate.ratingCount) || null : null;
        }
      }
    } catch (_) {
      continue;
    }
  }
  if (rating == null) {
    const value = metaContent("ratingValue");
    rating = value ? Number(value.replace(",", ".")) || null : null;
  }
  if (votes == null) {
    const count = metaContent("ratingCount");
    votes = count ? Number(count.replace(/[\\s]/g, "")) || null : null;
  }
  if (price == null) {
    const prices = [...(document.body.innerText || "").matchAll(/([\\d\\u00a0\\u2009\\s]{3,})\\s*₽/g)]
      .map((m) => Number(m[1].replace(/[\\u00a0\\u2009\\s]/g, "")) || null)
      .filter((value) => value != null && value > 0);
    price = prices.length ? prices[0] : null;
  }
  return JSON.stringify({
    id: location.pathname.match(/\\/(\\d+)(?:\\?|$)/)?.[1] || null,
    name,
    price,
    old_price: oldPrice,
    rating,
    rating_votes: votes,
    url: location.origin + location.pathname,
  });
})()
"""

OZON_BLOCKER = (
    "ozon failed the agent-browser spike: the antibot challenge page never "
    "resolves from this network (incident fab_chlg_*, evidence 2026-10-05); "
    "per the stop condition no bypass is implemented"
)


@dataclass(frozen=True)
class Marketplace:
    """One marketplace adapter: URLs, probes, extraction, and parsing."""

    name: str
    display_name: str
    host: str
    available: bool
    blocker: str | None
    search_url: Callable[[str, str], str]
    product_url: Callable[[str], str]
    probe_js: str
    extract_js: str
    product_js: str
    settle_ms: int = PROBE_SETTLE_MS
    lazy_scroll: bool = False

    def build_search_url(self, query: str, max_price: str) -> str:
        return self.search_url(query, max_price)

    def build_product_url(self, product_ref: str) -> str:
        return self.product_url(product_ref)

    def parse_items(
        self,
        raw: str,
        *,
        kind: str,
        query: str | None,
        limit: int,
    ) -> MarketplaceResult:
        """Parse one raw eval payload into the unified result envelope."""
        payload = _unwrap_payload(raw)
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise ExtractionFailed("extraction payload has no items list")
        items: list[ProductItem] = []
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            url = entry.get("url")
            if not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(url, str) or not url.startswith("http"):
                continue
            position = len(items) + 1
            item_id = entry.get("id")
            items.append(
                ProductItem(
                    position=position,
                    name=name.strip(),
                    url=url,
                    id=item_id if isinstance(item_id, str) else None,
                    price=parse_price(entry.get("price")),
                    old_price=parse_price(entry.get("old_price")),
                    rating=parse_rating(entry.get("rating")),
                    rating_votes=parse_rating_votes(entry.get("rating_votes")),
                )
            )
            if len(items) >= limit:
                break
        return MarketplaceResult(
            marketplace=self.name,
            kind=kind,
            items=tuple(items),
            query=query,
        )

    def parse_product(self, raw: str) -> ProductItem:
        """Parse one raw product-page payload into a unified item."""
        payload = _unwrap_payload(raw)
        name = payload.get("name")
        url = payload.get("url")
        if not isinstance(name, str) or not name.strip():
            raise ExtractionFailed("product payload has no name")
        if not isinstance(url, str) or not url.startswith("http"):
            raise ExtractionFailed("product payload has no URL")
        item_id = payload.get("id")
        return ProductItem(
            position=1,
            name=name.strip(),
            url=url,
            id=item_id if isinstance(item_id, str) else None,
            price=parse_price(payload.get("price")),
            old_price=parse_price(payload.get("old_price")),
            rating=parse_rating(payload.get("rating")),
            rating_votes=parse_rating_votes(payload.get("rating_votes")),
        )


def _unwrap_payload(raw: str) -> dict[str, object]:
    """Decode the double-encoded agent-browser eval output."""
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, str):
            decoded = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ExtractionFailed(f"extraction output is not JSON: {raw[:120]}") from exc
    if not isinstance(decoded, dict):
        raise ExtractionFailed("extraction output is not an object")
    return decoded


def _wildberries_search(query: str, max_price: str) -> str:
    return (
        "https://www.wildberries.ru/catalog/0/search.aspx"
        f"?search={quote(query)}&price=;{max_price}&sort=priceup"
    )


def _wildberries_product(product_ref: str) -> str:
    return f"https://www.wildberries.ru/catalog/{quote(product_ref)}/detail.aspx"


def _yandex_search(query: str, max_price: str) -> str:
    return f"https://market.yandex.ru/search?text={quote(query)}&price=;{max_price}"


def _yandex_product(product_ref: str) -> str:
    if product_ref.startswith("https://market.yandex.ru/"):
        return product_ref
    return f"https://market.yandex.ru/card/{quote(product_ref)}"


WILDBERRIES = Marketplace(
    name="wildberries",
    display_name="Wildberries",
    host="www.wildberries.ru",
    available=True,
    blocker=None,
    search_url=_wildberries_search,
    product_url=_wildberries_product,
    probe_js=WILDBERRIES_PROBE_JS,
    extract_js=WILDBERRIES_EXTRACT_JS,
    product_js=WILDBERRIES_PRODUCT_JS,
    lazy_scroll=True,
)

YANDEX_MARKET = Marketplace(
    name="yandex-market",
    display_name="Yandex Market",
    host="market.yandex.ru",
    available=True,
    blocker=None,
    search_url=_yandex_search,
    product_url=_yandex_product,
    probe_js=YANDEX_PROBE_JS,
    extract_js=YANDEX_EXTRACT_JS,
    product_js=YANDEX_PRODUCT_JS,
)

OZON = Marketplace(
    name="ozon",
    display_name="Ozon",
    host="www.ozon.ru",
    available=False,
    blocker=OZON_BLOCKER,
    search_url=lambda query, max_price: f"https://www.ozon.ru/search/?text={quote(query)}",
    product_url=lambda product_ref: f"https://www.ozon.ru/product/{quote(product_ref)}",
    probe_js="(() => JSON.stringify({blocked: true, cards: 0}))()",
    extract_js="(() => JSON.stringify({items: []}))()",
    product_js="(() => JSON.stringify({}))()",
)

REGISTRY: dict[str, Marketplace] = {
    marketplace.name: marketplace for marketplace in (WILDBERRIES, YANDEX_MARKET, OZON)
}


def resolve(name: str) -> Marketplace:
    """Resolve a marketplace by name with an explicit unknown error."""
    marketplace = REGISTRY.get(name.strip().lower())
    if marketplace is None:
        supported = ", ".join(sorted(REGISTRY))
        raise InvalidInput(f"unknown marketplace {name!r}; supported: {supported}")
    return marketplace
