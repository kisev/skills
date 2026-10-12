"""The repository pin standard for prose assertions.

Three pin kinds are allowed, chosen by what the pin protects:

1. Prose pins protect wording, not wrapping. Normalize whitespace on both
   sides with `pin` (or `assert_pin`) so reflowing a paragraph cannot break
   the pin and wrapped text cannot dodge it.
2. Format pins protect exact layout (YAML indentation, fenced blocks,
   rendered Markdown structure). Keep them as raw substring checks.
3. Classification pins only ask which name or category appears. Compare on
   `.lower()` and never mix them with prose pins.

Every new prose pin uses this module, so the marker inventory of a wave is
mechanical: `grep -rn "assert_pin\\|pin(" tests/` lists the standardized
pins, raw multi-line `in` asserts are format pins, and `.lower()` asserts
are classifications.
"""

from __future__ import annotations


def pin(text: str) -> str:
    """Collapse every whitespace run to one space; the prose pin normalizer."""
    return " ".join(text.split())


def assert_pin(haystack: str, needle: str, where: str = "") -> None:
    """Assert a reflow-safe prose containment pin."""
    assert pin(needle) in pin(haystack), where or needle
