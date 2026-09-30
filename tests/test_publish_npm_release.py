from __future__ import annotations

import time
from typing import Any

import pytest

from scripts import publish_npm_release


def _with_dist_tags(monkeypatch: pytest.MonkeyPatch, tags: Any) -> None:
    monkeypatch.setattr(publish_npm_release, "request_json", lambda url: {"dist-tags": tags})


def test_latest_tag_stable_accepts_stable_and_missing_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for tags in (
        {"latest": "10.1.0", "dev": "11.0.0-dev.48.gf6e4f0e086aa"},
        {"dev": "1.0.0-dev.48.gf6e4f0e086aa"},
    ):
        monkeypatch.setattr(
            publish_npm_release,
            "request_json",
            lambda url, payload=tags: {
                "dist-tags": payload,
                "versions": {"10.1.0": {}, "11.0.0-dev.48.gf6e4f0e086aa": {}},
            },
        )
        publish_npm_release.verify_latest_tag_stable(
            "@kisev/agentomatic", deadline=time.monotonic() + 1
        )


def test_latest_tag_stable_accepts_prerelease_without_stable_releases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_dist_tags(
        monkeypatch,
        {"latest": "1.0.0-dev.48.gf6e4f0e086aa", "dev": "1.0.0-dev.48.gf6e4f0e086aa"},
    )
    monkeypatch.setattr(
        publish_npm_release,
        "request_json",
        lambda url: {
            "dist-tags": {"latest": "1.0.0-dev.48.gf6e4f0e086aa"},
            "versions": {"1.0.0-dev.46.gfbe1e4c6992e": {}, "1.0.0-dev.48.gf6e4f0e086aa": {}},
        },
    )
    publish_npm_release.verify_latest_tag_stable("@kisev/safe-fs", deadline=time.monotonic() + 1)


def test_latest_tag_stable_rejects_prerelease_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        publish_npm_release,
        "request_json",
        lambda url: {
            "dist-tags": {"latest": "11.0.0-dev.46.gfbe1e4c6992e"},
            "versions": {"10.1.0": {}, "11.0.0-dev.46.gfbe1e4c6992e": {}},
        },
    )
    with pytest.raises(publish_npm_release.PublicationError, match="prerelease"):
        publish_npm_release.verify_latest_tag_stable(
            "@kisev/agentomatic", deadline=time.monotonic() + 1
        )


def test_latest_tag_stable_rejects_malformed_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_dist_tags(monkeypatch, {"latest": 11})
    with pytest.raises(publish_npm_release.PublicationError, match="invalid"):
        publish_npm_release.verify_latest_tag_stable(
            "@kisev/agentomatic", deadline=time.monotonic() + 1
        )
