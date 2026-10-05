"""Unified marketplace result schema shared by every shopmatic tool."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from math import isinf, isnan

from shopmatic.errors import InvalidInput

SCHEMA = "kisev-skills/shopmatic-result/v1"
CURRENCY = "RUB"


@dataclass(frozen=True)
class ProductItem:
    """One product row in the unified schema; price fields may be unknown."""

    position: int
    name: str
    url: str
    id: str | None = None
    price: float | None = None
    old_price: float | None = None
    rating: float | None = None
    rating_votes: int | None = None
    currency: str = CURRENCY


@dataclass(frozen=True)
class MarketplaceResult:
    """Structured result of one marketplace query in the unified schema."""

    marketplace: str
    kind: str
    items: tuple[ProductItem, ...]
    query: str | None = None
    url: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema": SCHEMA,
            "marketplace": self.marketplace,
            "kind": self.kind,
            "query": self.query,
            "items": [asdict(item) for item in self.items],
        }
        if self.url is not None:
            payload["url"] = self.url
        if self.warnings:
            payload["warnings"] = list(self.warnings)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=1)

    def with_warnings(self, *warnings: str) -> MarketplaceResult:
        """Return a copy with additional warnings attached."""
        return MarketplaceResult(
            marketplace=self.marketplace,
            kind=self.kind,
            items=self.items,
            query=self.query,
            url=self.url,
            warnings=(*self.warnings, *warnings),
        )


def parse_price(raw: object) -> float | None:
    """Coerce an extraction price into a finite non-negative float or None."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if isnan(value) or isinf(value) or value < 0:
        return None
    return value


def parse_rating(raw: object) -> float | None:
    """Coerce an extraction rating into a finite value between 0 and 5."""
    value = parse_price(raw)
    if value is None or value > 5:
        return None
    return value


def parse_rating_votes(raw: object) -> int | None:
    """Coerce an extraction vote count into a non-negative int or None."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = int(raw)
    return value if value >= 0 else None


def validate_query(query: str) -> str:
    """Reject empty or oversized queries before any browser interaction."""
    trimmed = query.strip()
    if not trimmed:
        raise InvalidInput("query must not be empty")
    if len(trimmed) > 200:
        raise InvalidInput("query must not exceed 200 characters")
    return trimmed


def validate_max_price(raw: float | None) -> float | None:
    """Bound the optional price cap to a sane positive range."""
    if raw is None:
        return None
    if raw <= 0 or raw > 100_000_000:
        raise InvalidInput("max_price must be between 0 and 100000000")
    return raw


def validate_limit(raw: int) -> int:
    """Bound the requested result count."""
    if raw < 1 or raw > 50:
        raise InvalidInput("limit must be between 1 and 50")
    return raw
