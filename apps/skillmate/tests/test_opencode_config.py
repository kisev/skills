"""Golden tests for the config-fragment editor, from the legacy config-setup spec.

Each test pins one behavior of the retired integration's REQ-F-514:
non-destructive merges, preserved comments and foreign entries, reported
conflicts, and byte-identical repeated application.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from skillmate.opencode_config import (
    ConfigConflictError,
    ConfigError,
    ConfigFragment,
    FragmentEntry,
    apply_fragment,
    evaluate,
    parse_jsonc,
)

SAMPLE = """{
  // user theme
  "theme": "dark",
  "plugin": ["one",],
  "permission": {
    "edit": "allow",
    "bash": {
      "*": "deny" // keep denied
    }
  }
}
"""


def _fragment(*entries: FragmentEntry) -> ConfigFragment:
    return ConfigFragment(name="test", entries=entries)


def _load(text: str) -> dict[str, Any]:
    value = parse_jsonc(text)
    assert isinstance(value, dict)
    return cast("dict[str, Any]", value)


def test_absent_preset_is_added() -> None:
    fragment = _fragment(
        FragmentEntry(path=("permission", "bash"), key="git status", value="allow")
    )
    merged = apply_fragment(SAMPLE, fragment)
    assert _load(merged)["permission"]["bash"]["git status"] == "allow"


def test_repeated_application_is_a_byte_identical_noop() -> None:
    fragment = _fragment(
        FragmentEntry(path=("permission", "bash"), key="git status", value="allow"),
        FragmentEntry(path=(), key="schema", value=1),
    )
    once = apply_fragment(SAMPLE, fragment)
    twice = apply_fragment(once, fragment)
    assert twice == once


def test_conflicting_value_is_reported_and_never_merged() -> None:
    fragment = _fragment(FragmentEntry(path=(), key="theme", value="light"))
    with pytest.raises(ConfigConflictError, match="theme"):
        apply_fragment(SAMPLE, fragment)


def test_comments_and_foreign_entries_survive_the_merge() -> None:
    fragment = _fragment(
        FragmentEntry(path=("permission", "bash"), key="git status", value="allow"),
        FragmentEntry(path=("experimental",), key="feature", value=True),
    )
    merged = apply_fragment(SAMPLE, fragment)
    assert "// user theme" in merged
    assert "// keep denied" in merged
    assert '"theme": "dark"' in merged
    assert '"plugin": ["one",]' in merged
    assert '"edit": "allow"' in merged


def test_comma_lands_before_a_trailing_line_comment() -> None:
    fragment = _fragment(
        FragmentEntry(path=("permission", "bash"), key="git status", value="allow")
    )
    merged = apply_fragment(SAMPLE, fragment)
    assert '"*": "deny", // keep denied' in merged
    assert '"git status": "allow"' in merged


def test_missing_path_chain_is_created_once() -> None:
    fragment = _fragment(
        FragmentEntry(path=("experimental", "deep", "deeper"), key="flag", value="x"),
        FragmentEntry(path=("experimental",), key="feature", value=True),
    )
    merged = apply_fragment(SAMPLE, fragment)
    parsed = _load(merged)
    assert parsed["experimental"] == {
        "feature": True,
        "deep": {"deeper": {"flag": "x"}},
    }
    assert merged.count('"experimental"') == 1


def test_written_document_reparses_as_jsonc() -> None:
    fragment = _fragment(
        FragmentEntry(path=("permission", "bash"), key="git status", value="allow"),
        FragmentEntry(path=("experimental",), key="nested", value={"a": [1, 2]}),
    )
    merged = apply_fragment(SAMPLE, fragment)
    assert isinstance(_load(merged), dict)


def test_empty_container_receives_the_preset() -> None:
    fragment = _fragment(FragmentEntry(path=("settings",), key="mode", value="auto"))
    merged = apply_fragment('{"settings": {}}\n', fragment)
    assert _load(merged) == {"settings": {"mode": "auto"}}
    assert apply_fragment(merged, fragment) == merged


def test_evaluate_reports_without_touching_the_document() -> None:
    fragment = _fragment(
        FragmentEntry(path=(), key="absent", value=1),
        FragmentEntry(path=(), key="theme", value="light"),
    )
    evaluation = evaluate(SAMPLE, fragment)
    assert evaluation.operations == ("set absent",)
    assert evaluation.conflicts == ("theme: present value differs from the fragment preset",)
    assert not evaluation.clean


def test_fragment_container_that_is_not_an_object_is_rejected() -> None:
    fragment = _fragment(FragmentEntry(path=("plugin",), key="extra", value=True))
    with pytest.raises(ConfigError, match="not an object"):
        evaluate(SAMPLE, fragment)


def test_broken_document_fails_loudly() -> None:
    with pytest.raises(ConfigError):
        parse_jsonc("{oops")


def test_block_comments_are_preserved() -> None:
    document = '{\n  /* keep */ "a": 1\n}\n'
    fragment = _fragment(FragmentEntry(path=(), key="b", value=2))
    merged = apply_fragment(document, fragment)
    assert "/* keep */" in merged
    assert _load(merged) == {"a": 1, "b": 2}
