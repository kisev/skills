"""Explicit terminal states for shopmatic operations."""

from __future__ import annotations


class ShopmaticError(Exception):
    """Base error carrying a user-facing message without internal detail."""


class InvalidInput(ShopmaticError):
    """A tool argument failed validation before any browser interaction."""


class BrowserUnavailable(ShopmaticError):
    """The agent-browser CLI is missing or failed to answer a command."""


class BrowserTimeout(BrowserUnavailable):
    """An agent-browser command exceeded its bounded timeout."""


class RenderFailed(ShopmaticError):
    """The marketplace SPA did not render searchable results in time."""


class ExtractionFailed(ShopmaticError):
    """The rendered page did not yield a parseable extraction payload."""


class AnonymityViolated(ShopmaticError):
    """A fresh profile was not empty before the first navigation."""


class MarketplaceBlocked(ShopmaticError):
    """The marketplace passed neither the spike nor anonymous access."""
